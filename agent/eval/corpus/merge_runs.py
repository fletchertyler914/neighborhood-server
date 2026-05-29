"""Merge pass/fail from multiple corpus runs (best-of per case_id)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge_envelopes(run_dirs: list[Path]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for run_dir in run_dirs:
        path = run_dir / "envelopes.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = row["case_id"]
            if cid not in merged or row.get("ok"):
                merged[cid] = row
    return merged


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Merge corpus run envelopes")
    parser.add_argument("runs", nargs="+", type=Path, help="corpus run directories")
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "agent" / "eval" / "corpus" / "baseline.json",
    )
    args = parser.parse_args()
    run_dirs = [p.resolve() for p in args.runs]
    merged = merge_envelopes(run_dirs)
    passed = sum(1 for r in merged.values() if r.get("ok"))
    total = len(merged)
    baseline = {
        "schema_version": 1,
        "merged_from": [p.name for p in run_dirs],
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        },
        "cases": {
            cid: {
                "ok": row.get("ok"),
                "primary_failure": row.get("primary_failure"),
                "status": row.get("status"),
            }
            for cid, row in sorted(merged.items())
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(baseline["summary"], indent=2))


if __name__ == "__main__":
    main()
