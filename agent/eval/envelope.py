"""Canonical job envelope merging eval results and audit logs."""

from __future__ import annotations

from typing import Any

from agent.eval.audit import read_audit_by_job_id
from agent.tool_registry import TOOLS_VERSION


def build_job_envelope(
    *,
    case_id: str,
    mode: str,
    job_id: str | None,
    status: str,
    steps: int,
    model: str,
    trace: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    prompt: str | None = None,
    strategy_id: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    audit = read_audit_by_job_id(job_id) if job_id else None
    return {
        "schema_version": 1,
        "tools_version": TOOLS_VERSION,
        "case_id": case_id,
        "mode": mode,
        "job_id": job_id,
        "status": status,
        "steps": steps,
        "model": model or (audit or {}).get("model", ""),
        "prompt": prompt or (audit or {}).get("prompt", ""),
        "strategy_id": strategy_id,
        "prompt_version": prompt_version,
        "trace": trace,
        "failures": failures,
        "audit": audit,
        "message": (audit or {}).get("message", ""),
    }
