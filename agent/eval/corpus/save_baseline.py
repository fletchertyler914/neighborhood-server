"""Write agent/eval/corpus/baseline.json from a corpus run report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def save_baseline(*, run_dir: Path, out_path: Path) -> dict:
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    summary = report["summary"]
    baseline = {
        "schema_version": 1,
        "timestamp": report.get("timestamp"),
        "run_dir": run_dir.name,
        "model": report.get("results", [{}])[0].get("model", "ollama:qwen2.5:7b-instruct"),
        "tools_version": report.get("tools_version"),
        "player": report.get("player"),
        "summary": summary,
        "cases": {
            r["case_id"]: {
                "ok": r["ok"],
                "status": r.get("status"),
                "steps": r.get("steps"),
                "primary_failure": r.get("primary_failure"),
            }
            for r in report.get("results", [])
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return baseline


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Save corpus baseline JSON")
    parser.add_argument(
        "--run",
        type=Path,
        default=root / "data" / "corpus-runs" / "latest",
        help="Corpus run directory or 'latest' symlink",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "agent" / "eval" / "corpus" / "baseline.json",
    )
    args = parser.parse_args()
    run_dir = args.run.resolve()
    baseline = save_baseline(run_dir=run_dir, out_path=args.out.resolve())
    print(
        json.dumps(
            {
                "out": str(args.out),
                "pass_rate": baseline["summary"]["pass_rate"],
                "total": baseline["summary"]["total"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
