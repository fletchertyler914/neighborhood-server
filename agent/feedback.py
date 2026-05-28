"""Human feedback collection for agent jobs.

The agent finishes a job, the player rates it with ``/agent good`` or
``/agent bad <why>``, and we persist the rating alongside the original
job's audit entry. The data is later turned into training pairs (SFT-style)
by ``agent.training.feedback``.

Storage is a JSON-lines file at ``data/agent-feedback.jsonl``. Each line is
a self-contained rating record so the file can be appended atomically
without locking and read incrementally for fine-tuning pipelines.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

from agent.safety import audit_log_path, utc_now_iso

Rating = Literal["good", "bad"]


def routing_from_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Extract routing metadata written by the orchestrator audit entry."""

    routing = audit.get("routing")
    if isinstance(routing, dict):
        return dict(routing)
    return {}


@dataclass
class FeedbackEntry:
    feedback_id: str
    job_id: str
    timestamp: str
    player: str
    rating: Rating
    note: str = ""
    prompt: str = ""
    tool_names: list[str] = field(default_factory=list)
    model: str = ""
    source: str = "chat"  # "chat" | "api" | "eval"
    routing: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "feedback_id": self.feedback_id,
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "player": self.player,
            "rating": self.rating,
            "note": self.note,
            "prompt": self.prompt,
            "tool_names": self.tool_names,
            "model": self.model,
            "source": self.source,
        }
        if self.routing:
            payload["routing"] = self.routing
        return json.dumps(payload, ensure_ascii=False)


def feedback_log_path() -> Path:
    root = Path(os.environ.get("NEIGHBORHOOD_REPO", Path(__file__).resolve().parents[1]))
    log_dir = root / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "agent-feedback.jsonl"


_write_lock = threading.Lock()


def append_feedback(entry: FeedbackEntry) -> Path:
    path = feedback_log_path()
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")
    return path


def iter_feedback() -> Iterator[dict[str, Any]]:
    path = feedback_log_path()
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# --- last-job tracking ---------------------------------------------------

# In-process state. Refreshed lazily from the audit log on cold start so
# feedback survives an orchestrator restart.
_last_job_by_player: dict[str, str] = {}
_last_job_lock = threading.Lock()
_audit_loaded = False


def remember_last_job(player: str, job_id: str) -> None:
    """Record the most recent successful job a player kicked off."""
    if not player or not job_id:
        return
    with _last_job_lock:
        _last_job_by_player[player.lower()] = job_id


def _player_key(player: str) -> str:
    return (player or "").lower()


def _hydrate_from_audit() -> None:
    """Replay the audit log to find each player's most recent job_id.

    Cheap on a fresh server, O(audit_log_lines). We only do this once per
    process; subsequent feedback updates the in-memory map directly.
    """
    global _audit_loaded
    if _audit_loaded:
        return
    path = audit_log_path()
    if not path.exists():
        _audit_loaded = True
        return
    try:
        # Read everything; the audit log is appended sequentially and we
        # need the *last* job per player.
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                player = obj.get("player") or ""
                job_id = obj.get("job_id") or obj.get("uuid")
                if not player or not job_id:
                    continue
                # Skip ratings themselves so we don't echo them back as the
                # job-to-rate.
                if obj.get("status") == "feedback":
                    continue
                _last_job_by_player[_player_key(player)] = job_id
    except OSError:
        pass
    finally:
        _audit_loaded = True


def get_last_job(player: str) -> str | None:
    _hydrate_from_audit()
    with _last_job_lock:
        return _last_job_by_player.get(_player_key(player))


def lookup_audit_entry(job_id: str) -> dict[str, Any] | None:
    """Find the audit entry for a job_id (last occurrence wins)."""
    path = audit_log_path()
    if not path.exists():
        return None
    found: dict[str, Any] | None = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("job_id") == job_id or obj.get("uuid") == job_id:
                    found = obj
    except OSError:
        return None
    return found


# --- prompt detection ----------------------------------------------------

_RATING_PATTERNS: tuple[tuple[re.Pattern[str], Rating], ...] = (
    (re.compile(r"^\s*(?:rate\s+)?good(?:\s+job)?\b", re.I), "good"),
    (re.compile(r"^\s*nice(?:\s+job)?\b", re.I), "good"),
    (re.compile(r"^\s*great(?:\s+job)?\b", re.I), "good"),
    (re.compile(r"^\s*perfect\b", re.I), "good"),
    (re.compile(r"^\s*\u2705|^\s*\U0001f44d", re.I), "good"),
    (re.compile(r"^\s*(?:rate\s+)?bad(?:\s+job)?\b", re.I), "bad"),
    (re.compile(r"^\s*wrong\b", re.I), "bad"),
    (re.compile(r"^\s*\u274c|^\s*\U0001f44e", re.I), "bad"),
    (re.compile(r"^\s*did\s*n[o']t\s+work\b", re.I), "bad"),
    (re.compile(r"^\s*broke\s+(it|that)\b", re.I), "bad"),
)


@dataclass
class ParsedRating:
    rating: Rating
    note: str


def parse_rating_prompt(prompt: str) -> ParsedRating | None:
    """Detect ``/agent good``, ``/agent bad <why>`` and friends.

    Returns ``None`` if the prompt is not a rating. Otherwise returns the
    parsed rating plus any trailing note text the player included.
    """
    if not prompt:
        return None
    text = prompt.strip()
    for pat, rating in _RATING_PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        note = text[m.end():].strip()
        # Trim a leading punctuation that often separates rating + note.
        note = re.sub(r"^[:,\-\u2014\s]+", "", note)
        return ParsedRating(rating=rating, note=note)
    return None


def record_feedback(
    *,
    player: str,
    rating: Rating,
    job_id: str | None = None,
    note: str = "",
    source: str = "chat",
) -> FeedbackEntry:
    """Resolve the target job, persist the rating, return the entry."""
    if rating not in ("good", "bad"):
        raise ValueError("rating must be 'good' or 'bad'")
    resolved_job_id = job_id or get_last_job(player)
    if not resolved_job_id:
        raise LookupError(
            "no recent job to rate for this player. Run an /agent action first."
        )
    audit = lookup_audit_entry(resolved_job_id) or {}
    tool_names = [
        tc.get("name", "") for tc in (audit.get("tool_calls") or []) if tc.get("name")
    ]
    routing = routing_from_audit(audit)
    entry = FeedbackEntry(
        feedback_id=str(uuid.uuid4()),
        job_id=resolved_job_id,
        timestamp=utc_now_iso(),
        player=player,
        rating=rating,
        note=note or "",
        prompt=audit.get("prompt", ""),
        tool_names=tool_names,
        model=audit.get("model", ""),
        source=source,
        routing=routing,
    )
    append_feedback(entry)
    return entry
