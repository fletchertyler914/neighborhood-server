"""Cluster corpus failures and emit triage.md with fix suggestions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_report(report_path: Path) -> dict[str, Any]:
    return json.loads(report_path.read_text(encoding="utf-8"))


def triage_report(report: dict[str, Any]) -> dict[str, Any]:
    results = report.get("results") or []
    failures = [r for r in results if not r.get("ok")]
    by_kind: Counter[str] = Counter()
    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for r in failures:
        kind = r.get("primary_failure") or "unknown"
        by_kind[kind] += 1
        by_category[r.get("category", "?")][kind] += 1
        if len(examples[kind]) < 5:
            examples[kind].append(
                {
                    "case_id": r.get("case_id"),
                    "prompt": r.get("prompt"),
                    "failures": r.get("failures"),
                    "trace": r.get("trace"),
                }
            )

    suggestions = _suggestions(by_kind, examples)
    return {
        "summary": report.get("summary", {}),
        "failure_counts": dict(by_kind.most_common()),
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "examples": dict(examples),
        "suggestions": suggestions,
    }


def _suggestions(
    by_kind: Counter[str],
    examples: dict[str, list[dict[str, Any]]],
) -> list[str]:
    out: list[str] = []
    if by_kind.get("tool_selection_miss", 0) > 0:
        out.append(
            "Review `agent/prompts/system.md` word-routing table and add few-shot "
            "examples for the top failing intents."
        )
    if by_kind.get("template_unresolved", 0) > 0:
        out.append(
            "Add catalog aliases in `agent/templates/catalog.json` for hallucinated "
            "template ids seen in failures."
        )
    if by_kind.get("world_state_wrong", 0) > 0:
        out.append(
            "Tune `world_probe` expectations or fix tool implementations so builds "
            "land in the probed sandbox cell."
        )
    if by_kind.get("no_tool_calls", 0) > 0:
        out.append(
            "Add orchestrator retry-on-empty-tool-calls or strengthen system prompt "
            "with explicit 'always call a tool' rule."
        )
    if by_kind.get("server_error", 0) > 0:
        out.append(
            "Inspect FAWE/RCON errors in traces; may need schema fixes or volume caps."
        )
    for kind, rows in examples.items():
        if not rows:
            continue
        sample = rows[0]
        out.append(f"Example `{kind}`: {sample.get('case_id')} — {sample.get('prompt', '')[:80]}")
    return out


def write_triage_md(triage: dict[str, Any], out_path: Path) -> None:
    lines: list[str] = [
        "# Corpus triage report",
        "",
        f"Pass rate: **{triage.get('summary', {}).get('pass_rate', 0):.1%}** "
        f"({triage.get('summary', {}).get('passed', 0)}/"
        f"{triage.get('summary', {}).get('total', 0)})",
        "",
        "## Failure buckets",
        "",
    ]
    for kind, count in sorted(
        (triage.get("failure_counts") or {}).items(),
        key=lambda x: -x[1],
    ):
        lines.append(f"- `{kind}`: {count}")
    lines.extend(["", "## Suggested fixes", ""])
    for s in triage.get("suggestions") or []:
        lines.append(f"- {s}")
    lines.extend(["", "## Examples by bucket", ""])
    for kind, rows in (triage.get("examples") or {}).items():
        lines.append(f"### {kind}")
        for row in rows[:3]:
            lines.append(f"- `{row.get('case_id')}`: {row.get('prompt', '')[:100]}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def triage_run(run_dir: Path) -> Path:
    report_path = run_dir / "report.json"
    if not report_path.exists():
        raise FileNotFoundError(report_path)
    triage = triage_report(load_report(report_path))
    out = run_dir / "triage.md"
    write_triage_md(triage, out)
    (run_dir / "triage.json").write_text(
        json.dumps(triage, indent=2, sort_keys=True), encoding="utf-8"
    )
    return out


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Triage corpus run failures")
    parser.add_argument(
        "--run",
        type=Path,
        default=Path("data/corpus-runs/latest"),
        help="Corpus run directory (contains report.json)",
    )
    args = parser.parse_args()
    run_dir = args.run.resolve()
    if run_dir.name == "latest" and run_dir.is_symlink():
        run_dir = run_dir.resolve()
    out = triage_run(run_dir)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
