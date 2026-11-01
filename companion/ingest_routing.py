"""Ops-gated deterministic route: ingest a schematic URL into the catalog.

Kids without ``neighborhood.agent.ingest`` (or qa) get a simple refusal.
Ops can paste SchemCraft / Bloxelizer / allowlisted URLs in chat:

  /ai ingest https://www.schemcraft.com/schematics/...
  /ai ingest https://bloxelizer.com/schematics/<slug> Small Windmill
  /ai ingest <url> as chicken_coop_small
  /ai ingest <url> as chicken_coop_small Small chicken coop
  /ai add schem <url>
  /ai add template <url> as chicken_coop_small
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from companion.dimensions import strip_politeness
from companion.ingest_schem import url_allowlisted
from companion.routing import RouteDecision

_URL_RE = re.compile(r"(https?://\S+|/[^ \t\n]+\.(?:schem|zip|litematic))", re.I)

# ingest <url> [title…] [as <id>]
# add schem <url>
# add template <url> [as <id>] [title…]
_INGEST_RE = re.compile(
    r"^(?:please\s+)?"
    r"(?:"
    r"ingest"
    r"|add\s+(?:schem(?:atic)?|template)"
    r"|import\s+(?:schem(?:atic)?|template)"
    r")"
    r"\s+(?P<body>.+)$",
    re.I,
)
_TID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,62}$", re.I)
_AS_ID_ONLY_RE = re.compile(
    r"^as\s+(?P<tid>[a-z0-9][a-z0-9_\-]{1,62})\s*$",
    re.I,
)
_AS_ID_THEN_TITLE_RE = re.compile(
    r"^as\s+(?P<tid>[a-z0-9][a-z0-9_\-]{1,62})\s+(?P<title>.+)$",
    re.I,
)
_TITLE_THEN_AS_RE = re.compile(
    r"^(?P<title>.+?)\s+as\s+(?P<tid>[a-z0-9][a-z0-9_\-]{1,62})\s*$",
    re.I,
)
_QUOTED_TITLE_RE = re.compile(r"^([\"'])(?P<title>.+)\1\s*$")


@dataclass(frozen=True)
class IngestAsk:
    url: str
    template_id: str | None = None
    title: str | None = None


def _clean_title(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = " ".join(raw.strip().split())
    if not text:
        return None
    quoted = _QUOTED_TITLE_RE.match(text)
    if quoted:
        text = quoted.group("title").strip()
    # Reject accidental template-id-only leftovers mistaken for titles.
    if _TID_RE.match(text) and "_" in text and text == text.lower():
        return None
    if len(text) > 80:
        text = text[:80].rstrip()
    return text or None


def _normalize_tid(raw: str | None) -> str | None:
    if not raw:
        return None
    tid = raw.strip().lower().replace("-", "_")
    if not _TID_RE.match(tid):
        return None
    return tid


def parse_ingest_prompt(prompt: str) -> IngestAsk | None:
    text = strip_politeness(" ".join((prompt or "").strip().split()))
    match = _INGEST_RE.match(text)
    if match is None:
        return None
    body = match.group("body").strip().rstrip(".!")
    url_match = _URL_RE.search(body)
    if url_match is None:
        return None
    url = url_match.group(1).rstrip(").,>]\"'")
    rest = body[url_match.end() :].strip().rstrip(".!")

    template_id: str | None = None
    title: str | None = None
    if rest:
        as_title = _AS_ID_THEN_TITLE_RE.match(rest)
        as_only = _AS_ID_ONLY_RE.match(rest)
        title_as = _TITLE_THEN_AS_RE.match(rest)
        if as_title:
            template_id = _normalize_tid(as_title.group("tid"))
            title = _clean_title(as_title.group("title"))
        elif as_only:
            template_id = _normalize_tid(as_only.group("tid"))
        elif title_as:
            title = _clean_title(title_as.group("title"))
            template_id = _normalize_tid(title_as.group("tid"))
        else:
            # Bare trailing text → display title
            # ("ingest <url> Small Windmill").
            title = _clean_title(rest)
            # If the only token looks like a catalog id, treat as id not title.
            if title is None and _normalize_tid(rest):
                template_id = _normalize_tid(rest)
            elif (
                title
                and " " not in title
                and _normalize_tid(title)
                and "_" in title
            ):
                template_id = _normalize_tid(title)
                title = None

    return IngestAsk(url=url, template_id=template_id, title=title)


def route_ingest(prompt: str, *, can_ingest: bool) -> RouteDecision | None:
    """Tier-S ops ingest. Returns None when the prompt is not an ingest ask."""
    ask = parse_ingest_prompt(prompt)
    if ask is None:
        return None
    if not can_ingest:
        return RouteDecision(
            route="ops.ingest.denied",
            tier="S",
            message="Only ops can add schematics. Ask an adult/op to run that.",
        )
    ok, reason = url_allowlisted(ask.url)
    if not ok:
        return RouteDecision(
            route="ops.ingest.bad_url",
            tier="S",
            message=(
                "I can only ingest SchemCraft, Bloxelizer, Shulkr, or a direct "
                f".schem/.zip link. ({reason})"
            ),
        )
    return RouteDecision(
        route="ops.ingest",
        tier="S",
        pending_slots={
            "url": ask.url,
            "template_id": ask.template_id or "",
            "title": ask.title or "",
        },
        message="",  # filled by app after in-process ingest
    )


def format_ingest_reply(
    *,
    template_id: str,
    title: str,
    aliases: list[str] | None,
    gold: bool,
) -> str:
    phrases = [a for a in (aliases or []) if a and len(a) < 40][:4]
    try_line = ""
    if phrases:
        try_line = " Try: " + " · ".join(phrases)
    star = " ★ gold" if gold else ""
    return (
        f"Added {title} (`{template_id}`){star}.{try_line} "
        f"Say build me a {phrases[0] if phrases else title.lower()} to paste."
    )[:220]
