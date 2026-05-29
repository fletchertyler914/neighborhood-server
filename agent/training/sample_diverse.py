"""Re-run failing corpus prompts at multiple temperatures for DPO diversity."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.eval.corpus_loader import load_corpus
from agent.eval.corpus_runner import run_corpus


DEFAULT_TEMPS = [0.0, 0.3, 0.7]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_report(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "report.json"
    return json.loads(path.read_text(encoding="utf-8"))


def failing_case_ids(report: dict[str, Any]) -> list[str]:
    return [r["case_id"] for r in report.get("results", []) if not r.get("ok")]


def sample_diverse(
    *,
    run_dir: Path,
    temperatures: list[float] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or _repo_root()
    run_dir = run_dir.resolve()
    if run_dir.name == "latest":
        run_dir = run_dir.resolve()
    report = load_report(run_dir)
    fail_ids = failing_case_ids(report)
    if not fail_ids:
        return {"resampled": 0, "message": "no failures to resample"}

    temps = temperatures or DEFAULT_TEMPS
    loaded = load_corpus(root / "agent" / "eval" / "corpus")
    id_set = set(fail_ids)
    prompts_by_id = {c.id: c for c in loaded.cases if c.id in id_set}

    out_dir = run_dir / "resampled"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, Any]] = []

    for temp in temps:
        for case_id in fail_ids:
            case = prompts_by_id.get(case_id)
            if case is None:
                continue
            os.environ["AGENT_CORPUS_LIMIT"] = "1"
            payload = run_corpus(
                repo_root=root,
                case_id=case_id,
                temperature=temp,
                output_dir=out_dir / f"t{str(temp).replace('.', '_')}_{case_id}",
            )
            for r in payload.get("results", []):
                r["sample_temperature"] = temp
                r["source_run"] = str(run_dir)
            all_results.extend(payload.get("results", []))

    combined = {
        "source_run": str(run_dir),
        "temperatures": temps,
        "case_ids": fail_ids,
        "results": all_results,
    }
    (out_dir / "combined.json").write_text(
        json.dumps(combined, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {"resampled": len(all_results), "output_dir": str(out_dir), "temperatures": temps}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Resample failing corpus cases at varied temperatures")
    parser.add_argument("--run", type=Path, default=Path("data/corpus-runs/latest"))
    parser.add_argument("--temperatures", default="0.0,0.3,0.7")
    args = parser.parse_args()
    temps = [float(x.strip()) for x in args.temperatures.split(",") if x.strip()]
    result = sample_diverse(run_dir=args.run, temperatures=temps)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
