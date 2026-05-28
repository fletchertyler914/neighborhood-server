"""Append-only audit log for template ranking (tuning + feedback joins)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.templates.ranking import RankedTemplateResult

_ranking_lock = threading.Lock()


def ranking_audit_path() -> Path:
    root = Path(os.environ.get("NEIGHBORHOOD_REPO", Path(__file__).resolve().parents[2]))
    log_dir = root / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "template-ranking-audit.jsonl"


def _rotate_ranking_log(path: Path, *, max_bytes: int = 50 * 1024 * 1024) -> None:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return
    rotated = path.with_suffix(path.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    path.rename(rotated)


def append_ranking_audit(
    result: RankedTemplateResult,
    *,
    source: str = "resolve_template",
    extra: dict[str, Any] | None = None,
) -> str:
    """Append one ranking decision; returns decision_id for cross-log joins."""

    if os.environ.get("TEMPLATE_RANKING_AUDIT", "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return ""
    decision_id = str(uuid.uuid4())
    from agent.tool_registry import TOOLS_VERSION

    payload: dict[str, Any] = {
        "decision_id": decision_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "tools_version": TOOLS_VERSION,
        **result.to_dict(),
    }
    if extra:
        payload["extra"] = extra
    path = ranking_audit_path()
    with _ranking_lock:
        _rotate_ranking_log(path)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return decision_id
