"""Per-job routing metadata for audit, feedback, and training exports."""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()
_by_job: dict[str, "RoutingRecord"] = {}
_current_job: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "routing_current_job", default=None
)


def set_current_job(job_id: str | None) -> None:
    _current_job.set(job_id)


def current_routing() -> RoutingRecord | None:
    jid = _current_job.get()
    if not jid:
        return None
    return get_job(jid)


@dataclass
class RoutingRecord:
    intent_family: str = ""
    selected_tool: str = ""
    selected_template_id: str = ""
    fallback_reason: str = ""
    rewrite_applied: bool = False
    original_tool: str = ""
    source_id: str = ""
    content_hash: str = ""
    template_confidence: str = ""
    template_confidence_score: float = 0.0
    template_ranking: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "intent_family": self.intent_family,
            "selected_tool": self.selected_tool,
            "selected_template_id": self.selected_template_id,
            "fallback_reason": self.fallback_reason,
            "rewrite_applied": self.rewrite_applied,
            "original_tool": self.original_tool,
            "source_id": self.source_id,
            "content_hash": self.content_hash,
            **self.extra,
        }
        if self.template_confidence:
            out["template_confidence"] = self.template_confidence
        if self.template_confidence_score:
            out["template_confidence_score"] = self.template_confidence_score
        if self.template_ranking:
            out["template_ranking"] = self.template_ranking
        return out


def note_template_ranking(ranked: Any) -> None:
    """Attach hybrid ranker output to the active routing record."""

    rec = current_routing()
    if rec is None or ranked is None:
        return
    rec.template_confidence = str(getattr(ranked, "confidence", "") or "")
    rec.template_confidence_score = float(getattr(ranked, "confidence_score", 0.0) or 0.0)
    if hasattr(ranked, "to_dict"):
        rec.template_ranking = ranked.to_dict()
    tid = getattr(ranked, "selected_template_id", None)
    if tid:
        rec.selected_template_id = str(tid)
        note_template_provenance(str(tid))


def note_template_provenance(template_id: str) -> None:
    """Attach catalog provenance to the active routing record."""

    rec = current_routing()
    if rec is None or not template_id:
        return
    from agent.templates import catalog as template_catalog
    from agent.templates.pack_spec import file_content_hash

    try:
        meta = template_catalog.find_template(template_id)
    except ValueError:
        return
    rec.source_id = meta.source_id
    rec.content_hash = meta.content_hash
    if not rec.content_hash:
        local = template_catalog.schematic_repo_path(meta)
        if local.is_file():
            rec.content_hash = file_content_hash(local)


def start_job(job_id: str) -> RoutingRecord:
    rec = RoutingRecord()
    with _lock:
        _by_job[job_id] = rec
    return rec


def get_job(job_id: str) -> RoutingRecord | None:
    with _lock:
        return _by_job.get(job_id)


def finish_job(job_id: str) -> RoutingRecord | None:
    with _lock:
        return _by_job.pop(job_id, None)


def clear_all() -> None:
    with _lock:
        _by_job.clear()
