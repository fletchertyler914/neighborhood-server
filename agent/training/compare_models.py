"""Compare base vs fine-tuned models on the NL corpus."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.eval.corpus_runner import run_corpus


def _ollama_model_available(model: str) -> bool:
    """Return True if the model tag responds to Ollama's show API."""

    import os
    import shutil
    import subprocess
    import urllib.error
    import urllib.request

    tag = model.removeprefix("ollama:")
    base = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/show", data=json.dumps({"name": tag}).encode(), timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    if not shutil.which("ollama"):
        return False
    try:
        subprocess.run(
            ["ollama", "show", tag],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def compare_models_on_corpus(
    *,
    models: list[str],
    repo_root: Path | None = None,
    limit: int | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    results: dict[str, Any] = {}
    skipped: list[str] = []
    for model in models:
        tag = model.removeprefix("ollama:")
        if not _ollama_model_available(tag):
            skipped.append(model)
            continue
        payload = run_corpus(
            repo_root=root,
            model_override=model,
            limit=limit,
            category=category,
            output_dir=root / "data" / "corpus-runs" / f"compare_{model.replace(':', '_').replace('/', '_')}",
        )
        results[model] = payload["summary"]

    markdown = _markdown_table(results, skipped=skipped)
    out = root / "data" / "corpus-runs" / "compare_report.md"
    out.write_text(markdown, encoding="utf-8")
    return {"models": results, "skipped": skipped, "report_path": str(out)}


def _markdown_table(results: dict[str, Any], *, skipped: list[str] | None = None) -> str:
    lines = ["# Corpus model comparison", ""]
    if skipped:
        lines.append(
            "Skipped (Ollama tag not installed): "
            + ", ".join(f"`{m}`" for m in skipped)
        )
        lines.append("")
    lines.extend(["| Model | Passed | Total | Pass rate |", "| --- | ---: | ---: | ---: |"])
    for model, summary in results.items():
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        rate = summary.get("pass_rate", 0)
        lines.append(f"| `{model}` | {passed} | {total} | {rate:.1%} |")
    lines.append("")
    lines.append("## By category")
    for model, summary in results.items():
        lines.append(f"### {model}")
        for cat, stats in (summary.get("by_category") or {}).items():
            lines.append(f"- **{cat}**: {stats.get('passed', 0)}/{stats.get('total', 0)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compare models on corpus subset")
    parser.add_argument(
        "--models",
        default=os.environ.get(
            "AGENT_COMPARE_MODELS",
            "qwen2.5:7b-instruct,neighborhood-qwen2.5-7b:v1",
        ),
    )
    parser.add_argument("--limit", type=int, default=int(os.environ.get("AGENT_CORPUS_LIMIT", "50")))
    parser.add_argument("--category")
    args = parser.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    payload = compare_models_on_corpus(models=models, limit=args.limit, category=args.category)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
