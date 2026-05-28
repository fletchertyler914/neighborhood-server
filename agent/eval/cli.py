from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent.eval.compare import compare_variants
from agent.eval.export import export_jsonl
from agent.eval.runner import run
from agent.safety import audit_log_path


def _cmd_run(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    payload = run(
        repo_root=repo_root,
        orchestrator_url=args.orchestrator_url,
        api_token=args.api_token,
        mode=args.mode,
        case_id=args.case,
        category=args.category,
        player=args.player,
        uuid=args.uuid,
        write_report_dir=Path(args.json_out).resolve() if args.json_out else repo_root / "data" / "eval-runs" / "latest",
        compare_baseline=Path(args.compare_baseline).resolve() if args.compare_baseline else None,
        save_baseline=Path(args.save_baseline).resolve() if args.save_baseline else None,
        exit_on_fail=False,
        model_override=(args.model or None),
    )
    _print_summary(payload)


def _cmd_export(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    reports = [Path(p).resolve() for p in (args.report or [])]
    if not reports:
        default = repo_root / "data" / "eval-runs" / "latest" / "report.json"
        if default.exists():
            reports = [default]
    audit = Path(args.audit).resolve() if args.audit else audit_log_path()
    if not audit.exists():
        audit = repo_root / "data" / "agent-audit.log"
    out = Path(args.out).resolve()
    n = export_jsonl(out_path=out, report_paths=reports, audit_path=audit if audit.exists() else None)
    print(f"exported_rows={n} path={out}")


def _cmd_compare(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).resolve()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    variants = [
        {"label": m.replace(":", "_").replace("/", "_"), "model": m, "strategy": args.strategy}
        for m in models
    ]
    payload = compare_variants(
        repo_root=repo_root,
        orchestrator_url=args.orchestrator_url,
        api_token=args.api_token,
        variants=variants,
        mode=args.mode,
        output_dir=Path(args.json_out).resolve() if args.json_out else repo_root / "data" / "eval-runs" / "compare",
        compare_baseline=Path(args.compare_baseline).resolve() if args.compare_baseline else None,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload.get("winner"):
        raise SystemExit(2)


def _print_summary(payload: dict) -> None:
    summary = payload["summary"]
    print(f"cases={summary['total']} passed={summary['passed']} failed={summary['failed']}")
    diff = payload.get("baseline_diff")
    if diff:
        print(
            "baseline:",
            f"regressions={len(diff['regressions'])}",
            f"improvements={len(diff['improvements'])}",
            f"drift={len(diff['drift'])}",
        )
    if summary["failed"] or (diff and diff["regressions"]):
        raise SystemExit(2)


def main() -> None:
    # Legacy: `python -m agent.eval.cli spec` (no subcommand)
    if len(sys.argv) > 1 and sys.argv[1] in ("spec", "world", "both"):
        parser = argparse.ArgumentParser(description="Run Neighborhood agent evals")
        parser.add_argument("mode", choices=["spec", "world", "both"])
        parser.add_argument("--repo-root", default=os.environ.get("NEIGHBORHOOD_REPO", "."))
        parser.add_argument("--orchestrator-url", default=os.environ.get("AGENT_ORCH_URL", "http://127.0.0.1:8787"))
        parser.add_argument("--api-token", default=os.environ.get("AGENT_API_TOKEN", "dev-change-me"))
        parser.add_argument("--case")
        parser.add_argument("--category")
        parser.add_argument("--player", default=os.environ.get("AGENT_EVAL_PLAYER", ".EvalBot"))
        parser.add_argument("--uuid", default=os.environ.get("AGENT_EVAL_UUID", "00000000-0000-0000-0000-000000000000"))
        parser.add_argument("--json-out")
        parser.add_argument("--compare-baseline", default=os.environ.get("EVAL_COMPARE_BASELINE"))
        parser.add_argument("--save-baseline", default=os.environ.get("EVAL_SAVE_BASELINE"))
        parser.add_argument("--model", default=os.environ.get("AGENT_EVAL_MODEL_OVERRIDE", ""))
        _cmd_run(parser.parse_args())
        return

    parser = argparse.ArgumentParser(description="Neighborhood agent eval harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run spec/world/both eval suite")
    run_p.add_argument("mode", choices=["spec", "world", "both"], default="spec", nargs="?")
    run_p.add_argument("--repo-root", default=os.environ.get("NEIGHBORHOOD_REPO", "."))
    run_p.add_argument("--orchestrator-url", default=os.environ.get("AGENT_ORCH_URL", "http://127.0.0.1:8787"))
    run_p.add_argument("--api-token", default=os.environ.get("AGENT_API_TOKEN", "dev-change-me"))
    run_p.add_argument("--case")
    run_p.add_argument("--category")
    run_p.add_argument("--player", default=os.environ.get("AGENT_EVAL_PLAYER", ".EvalBot"))
    run_p.add_argument("--uuid", default=os.environ.get("AGENT_EVAL_UUID", "00000000-0000-0000-0000-000000000000"))
    run_p.add_argument("--json-out")
    run_p.add_argument("--compare-baseline")
    run_p.add_argument("--save-baseline")
    run_p.add_argument("--model", default=os.environ.get("AGENT_EVAL_MODEL_OVERRIDE", ""))
    run_p.set_defaults(func=_cmd_run)

    export_p = sub.add_parser("export", help="Export normalized JSONL for training/review")
    export_p.add_argument("--repo-root", default=os.environ.get("NEIGHBORHOOD_REPO", "."))
    export_p.add_argument("--out", default="datasets/reviews/raw/export.jsonl")
    export_p.add_argument("--report", action="append", default=[])
    export_p.add_argument("--audit", default="")
    export_p.set_defaults(func=_cmd_export)

    compare_p = sub.add_parser("compare", help="Compare multiple models on the same suite")
    compare_p.add_argument("--repo-root", default=os.environ.get("NEIGHBORHOOD_REPO", "."))
    compare_p.add_argument("--orchestrator-url", default=os.environ.get("AGENT_ORCH_URL", "http://127.0.0.1:8787"))
    compare_p.add_argument("--api-token", default=os.environ.get("AGENT_API_TOKEN", "dev-change-me"))
    compare_p.add_argument("--models", required=True, help="Comma-separated Ollama model names")
    compare_p.add_argument("--mode", choices=["spec", "world", "both"], default="spec")
    compare_p.add_argument("--strategy", default="baseline")
    compare_p.add_argument("--json-out")
    compare_p.add_argument("--compare-baseline")
    compare_p.set_defaults(func=_cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
