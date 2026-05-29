"""Export normalized training/review rows from eval reports and audit logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


def iter_report_rows(report_path: Path) -> Iterator[dict[str, Any]]:
    if not report_path.exists():
        return
    data = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = data.get("manifest") or {}
    strategy_id = data.get("strategy_id") or manifest.get("flags", {}).get(
        "AGENT_PROMPT_STRATEGY"
    )
    for env in data.get("envelopes") or []:
        yield {
            "schema_version": 1,
            "source": "job_envelope",
            **{k: v for k, v in env.items() if k != "audit"},
            "audit_job_id": (env.get("audit") or {}).get("job_id"),
        }
    for result in data.get("results") or []:
        yield {
            "schema_version": 1,
            "source": "eval_report",
            "tools_version": manifest.get("tools_version"),
            "strategy_id": strategy_id,
            "model": result.get("model") or manifest.get("model"),
            "case_id": result.get("case_id"),
            "mode": result.get("mode"),
            "ok": result.get("ok"),
            "status": result.get("status"),
            "steps": result.get("steps"),
            "job_id": result.get("job_id"),
            "prompt": result.get("prompt"),
            "trace": result.get("trace") or [],
            "trace_hash": result.get("trace_hash"),
            "failures": result.get("failures") or [],
            "manifest": manifest,
        }


def iter_audit_rows(audit_path: Path, *, limit: int = 5000) -> Iterator[dict[str, Any]]:
    if not audit_path.exists():
        return
    lines = audit_path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield {
            "schema_version": 1,
            "source": "audit_log",
            "job_id": obj.get("job_id"),
            "timestamp": obj.get("timestamp"),
            "player": obj.get("player"),
            "prompt": obj.get("prompt"),
            "status": obj.get("status"),
            "model": obj.get("model"),
            "steps": obj.get("steps"),
            "tool_calls": obj.get("tool_calls") or [],
            "message": obj.get("message"),
            "dry_run": obj.get("dry_run"),
        }


def export_jsonl(
    *,
    out_path: Path,
    report_paths: list[Path] | None = None,
    audit_path: Path | None = None,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for rp in report_paths or []:
            for row in iter_report_rows(rp):
                f.write(json.dumps(row, sort_keys=True) + "\n")
                count += 1
        if audit_path:
            for row in iter_audit_rows(audit_path):
                f.write(json.dumps(row, sort_keys=True) + "\n")
                count += 1
    return count
