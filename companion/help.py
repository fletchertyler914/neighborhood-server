"""Kid-friendly in-game playbook pages (deterministic Tier S).

Copy stays short for Minecraft chat. Build name lists are pulled from the gold
catalog so they stay fresh when titles change.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from companion.templates import reload_catalog

if TYPE_CHECKING:
    from companion.routing import RouteDecision

# Soft chat budget (Java ~256; leave room for "[Crafter] " prefix).
_MAX_CHARS = 220

# Catalog category → playbook bucket used by /agent help <topic> (or /ai help).
_CATALOG_BUCKETS: dict[str, str] = {
    "house": "houses",
    "farm": "farms",
    "fortress": "forts",
    "infrastructure": "bridges",
    "decoration": "parks",
    "nature_terrain": "nature",
    "utility": "utility",
}

_TOPIC_ALIASES: dict[str, str] = {
    "builds": "builds",
    "build": "builds",
    "building": "builds",
    "buildings": "builds",
    "ideas": "builds",
    "idea": "builds",
    "catalog": "builds",
    "templates": "builds",
    "places": "builds",
    "houses": "houses",
    "house": "houses",
    "homes": "houses",
    "home": "houses",
    "shops": "houses",
    "shop": "houses",
    "cottage": "houses",
    "cottages": "houses",
    "farms": "farms",
    "farm": "farms",
    "gardens": "farms",
    "garden": "farms",
    "animals": "farms",
    "pens": "farms",
    "forts": "forts",
    "fort": "forts",
    "fortress": "forts",
    "towers": "forts",
    "tower": "forts",
    "castles": "forts",
    "castle": "forts",
    "bridges": "bridges",
    "bridge": "bridges",
    "paths": "bridges",
    "path": "bridges",
    "docks": "bridges",
    "dock": "bridges",
    "parks": "parks",
    "park": "parks",
    "decoration": "parks",
    "decor": "parks",
    "nature": "nature",
    "trees": "nature",
    "tree": "nature",
    "utility": "utility",
    "utilities": "utility",
    "workshop": "utility",
    "workshops": "utility",
    "shapes": "shapes",
    "shape": "shapes",
    "walls": "shapes",
    "wall": "shapes",
    "platforms": "shapes",
    "platform": "shapes",
    "spawn": "spawn",
    "summon": "spawn",
    "mobs": "spawn",
    "mob": "spawn",
    "creatures": "spawn",
    "give": "give",
    "items": "give",
    "item": "give",
    "stuff": "give",
    "inventory": "give",
    "world": "world",
    "time": "world",
    "weather": "world",
    "day": "world",
    "night": "world",
    "tips": "tips",
    "tip": "tips",
    "howto": "tips",
    "how": "tips",
    "undo": "tips",
}

_MENU_RE = re.compile(
    r"^(?:"
    r"help(?:\s+me)?|"
    r"what\s+can\s+you\s+do|"
    r"what\s+do\s+you\s+do|"
    r"commands?|"
    r"what\s+are\s+(?:the\s+)?commands?|"
    r"how\s+do\s+(?:i|you)\s+work|"
    r"how\s+does\s+this\s+work"
    r")[.!?]?$",
    re.I,
)

_BUILDS_ENTRY_RE = re.compile(r"^(?:builds?|ideas?)[.!?]?$", re.I)

# Whitelist only — "help me build a house" must NOT match.
_TOPIC_WORD = (
    r"builds?|ideas?|catalog|templates?|places?|"
    r"houses?|homes?|shops?|cottages?|"
    r"farms?|gardens?|animals|pens?|"
    r"forts?|fortress(?:es)?|towers?|castles?|"
    r"bridges?|paths?|docks?|"
    r"parks?|decoration|decor|"
    r"nature|trees?|"
    r"utility|utilities|workshops?|"
    r"shapes?|walls?|platforms?|"
    r"spawn|summon|mobs?|creatures?|"
    r"give|items?|stuff|inventory|"
    r"world|time|weather|day|night|"
    r"tips?|howto|undo"
)

_TOPIC_RE = re.compile(
    rf"^(?:help(?:\s+me)?(?:\s+with)?|show(?:\s+me)?)\s+"
    rf"(?P<topic>{_TOPIC_WORD})"
    rf"(?:\s+and\s+[a-z]+)?"
    rf"(?:\s+(?P<page>\d+|more))?[.!?]?$",
    re.I,
)


def _clip(text: str, limit: int = _MAX_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(",;·")
    return (cut or text[: limit - 1]).rstrip() + "…"


@lru_cache(maxsize=1)
def _gold_titles() -> dict[str, tuple[str, ...]]:
    from companion.templates import _catalog

    buckets: dict[str, list[str]] = {name: [] for name in _CATALOG_BUCKETS.values()}
    for item in _catalog():
        if not item.get("gold"):
            continue
        bucket = _CATALOG_BUCKETS.get(str(item.get("category") or ""))
        if not bucket:
            continue
        title = str(item.get("title") or item.get("id") or "").strip()
        if title:
            buckets[bucket].append(title)
    return {key: tuple(sorted(set(values))) for key, values in buckets.items()}


def reload_help_catalog() -> None:
    """Drop cached title lists (tests / catalog reload)."""
    reload_catalog()
    _gold_titles.cache_clear()


def _title_page(bucket: str, page: int = 1, *, page_size: int = 10) -> str:
    titles = list(_gold_titles().get(bucket, ()))
    if not titles:
        return "I don't have builds in that group yet. Try: help builds"
    page = max(1, page)
    start = (page - 1) * page_size
    chunk = titles[start : start + page_size]
    if not chunk:
        return _clip(
            f"No more on page {page}. Try: help {bucket} or help builds"
        )
    more = start + page_size < len(titles)
    suffix = f" Say help {bucket} {page + 1} for more." if more else ""
    label = {
        "houses": "Houses & shops",
        "farms": "Farms & animals",
        "forts": "Forts & towers",
        "bridges": "Bridges & paths",
        "parks": "Parks & decor",
        "nature": "Nature",
        "utility": "Utility",
    }.get(bucket, bucket.title())
    return _clip(f"{label}: {', '.join(chunk)}.{suffix}")


def _page(topic: str, page: int = 1) -> str:
    if topic == "builds":
        return _clip(
            "Ready-made builds — open /builds to browse, or say the name! "
            "Also: help houses · help farms · help forts · help bridges · "
            "help parks · help nature · help utility"
        )
    if topic in {"houses", "farms", "forts", "bridges", "parks", "nature", "utility"}:
        return _title_page(topic, page)
    if topic == "shapes":
        return _clip(
            "Shapes near you: wall, platform, enclosure, box, tower, bridge, path. "
            "Try: start a path (place gold blocks, then finish the path) · "
            "make a bridge · cobblestone wall 20 long 5 high"
        )
    if topic == "spawn":
        return _clip(
            "Spawn living mobs (up to 20): chickens, cows, pigs, wolves, "
            "creepers, zombies, dragon… Try: spawn 3 chickens · summon a dragon"
        )
    if topic == "give":
        return _clip(
            "I can give normal items (up to 64). Try: give me 16 glass · "
            "give me a diamond sword · look at a block and say give me these blocks. "
            "Not admin blocks like command blocks."
        )
    if topic == "world":
        return _clip(
            "World stuff: day, noon, night, midnight · clear/sunny, rain, thunder. "
            "Try: make it daytime · stop the rain · make it night"
        )
    if topic == "tips":
        return _clip(
            "Stand where you want it. Browse with /builds, or say a name "
            "(chicken coop). Shapes: tower 10 tall. Oops? undo that. "
            "Still wrong? bad wrong_build"
        )
    return _clip(
        "Ask me: help builds · help shapes · help spawn · help give · "
        "help world · help tips"
    )


def _menu() -> str:
    return _clip(
        "Hi! I'm Crafter. Browse builds: /builds (or right-click my Build Book). "
        "Also: help builds · help shapes · help spawn · help give · help world · help tips"
    )


def route_help(text: str) -> RouteDecision | None:
    """Return a Tier-S help decision, or None if this isn't a help ask."""
    from companion.routing import RouteDecision

    if not text:
        return None
    if _MENU_RE.fullmatch(text):
        return RouteDecision(
            route="help.menu",
            tier="S",
            message=_menu(),
        )
    if _BUILDS_ENTRY_RE.fullmatch(text):
        return RouteDecision(
            route="help.builds",
            tier="S",
            message=_page("builds"),
        )
    topic_match = _TOPIC_RE.fullmatch(text)
    if topic_match:
        topic = _TOPIC_ALIASES.get(topic_match.group("topic").lower())
        if topic is None:
            return None
        page_token = (topic_match.group("page") or "1").lower()
        page = 2 if page_token == "more" else int(page_token)
        return RouteDecision(
            route=f"help.{topic}",
            tier="S",
            message=_page(topic, page),
        )
    return None
