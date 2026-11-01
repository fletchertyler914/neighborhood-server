"""Classify unfulfilled companion asks into coverage-gap reason codes."""

from __future__ import annotations

# Routes that are not coverage gaps (cancel/undo/help/interactive noise).
_SKIP_ROUTES = frozenset(
    {
        "grammar.cancel",
        "feedback",
        "native.clear_ask",
    }
)

_VALID_REASONS = frozenset(
    {"clarify", "unresolved", "refuse", "failed", "ingest"}
)


def classify_gap_reason(
    route: str,
    *,
    ok: bool,
    explicit: str | None = None,
) -> str | None:
    """Return a gap reason code, or None when the outcome should not be logged.

    ``explicit`` overrides auto-classification when provided (use ``\"\"`` to skip).
    """
    if ok:
        return None
    if explicit is not None:
        reason = explicit.strip().lower()
        if not reason:
            return None
        return reason if reason in _VALID_REASONS else "unresolved"

    r = (route or "").strip()
    if not r or r in _SKIP_ROUTES:
        return None
    if r.startswith("help."):
        return None
    if "undo" in r.lower():
        return None

    if r.startswith("ops.ingest"):
        return "ingest"
    if "refuse" in r or r.endswith(".unsupported") or "restricted" in r:
        return "refuse"
    if "clarify" in r:
        return "clarify"
    if r in {"unresolved", "model.unavailable", "model.invalid"}:
        return "unresolved"
    if r.startswith("model.") and r.endswith(".refuse"):
        return "refuse"
    # Routed action that failed verification/execution, or unknown failure.
    return "failed"
