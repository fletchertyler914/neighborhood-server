"""Append-only audit log for template ranking (tuning + feedback joins)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.templates.ranking import RankedTemplateResult


def ranking_audit_path() -> Path:
    root = Path(os.environ.get("NEIGHBORHOOD_REPO", Path(__file__).resolve().parents[2]))
    log_dir = root / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "template-ranking-audit.jsonl"


def append_ranking_audit(
    result: RankedTemplateResult,
    *,
    source: str = "resolve_template",
    extra: dict[str, Any] | None = None,
) -> None:
    if os.environ.get("TEMPLATE_RANKING_AUDIT", "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return
    payload: dict[str, Any] = {
        "source": source,
        **result.to_dict(),
    }
    if extra:
        payload["extra"] = extra
    path = ranking_audit_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
