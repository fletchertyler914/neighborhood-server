"""Audit log helpers for eval envelopes and export."""

from __future__ import annotations

import json
from typing import Any

from agent.safety import audit_log_path


def read_audit_by_job_id(job_id: str) -> dict[str, Any] | None:
    path = audit_log_path()
    if not path.exists():
        return None
    try:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()[-2000:]):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("job_id") == job_id:
                return obj
    except OSError:
        return None
    return None
