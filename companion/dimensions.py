"""Shared dimension / politeness / material tokenization for NL builds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_POLITE = re.compile(
    r"^\s*(?:(?:yo|hey|hi|please|pls|plz|could you|can you|would you)"
    r"(?:\s+please)?\s+)+",
    re.I,
)


def strip_politeness(text: str) -> str:
    cleaned = _POLITE.sub("", text.strip())
    cleaned = re.sub(r"\s+(?:please|pls|plz)[.!]?$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or text.strip()


_BAD_MATERIALS = frozenset(
    {
        "a",
        "an",
        "the",
        "me",
        "my",
        "this",
        "that",
        "here",
        "there",
        "some",
        "small",
        "big",
        "large",
        "little",
        "tall",
        "high",
        "long",
        "wide",
        "by",
        "x",
    }
)

# Trailing shape / dimension words that ride along material family matches
# ("oak platform", "stone box", "quartz cylinder radius").
_MATERIAL_TRAILING_NOISE = frozenset(
    {
        "wall",
        "walls",
        "platform",
        "pad",
        "deck",
        "raft",
        "box",
        "room",
        "shell",
        "cube",
        "tower",
        "pillar",
        "cylinder",
        "cyl",
        "floor",
        "floors",
        "block",
        "blocks",
        "radius",
        "height",
        "high",
        "tall",
        "long",
        "wide",
        "across",
        "solid",
        "hollow",
        "enclosure",
        "pen",
        "yard",
        "courtyard",
        "arena",
        "compound",
        "fence",
        "square",
        "rectangle",
        "bridge",
        "road",
        "path",
        "trail",
        "footpath",
        "walkway",
        "highway",
    }
)


def _strip_material_trailing_noise(raw: str) -> str:
    words = raw.strip().split()
    while words and words[-1].lower() in _MATERIAL_TRAILING_NOISE:
        words.pop()
    while words and re.fullmatch(r"\d+", words[-1]):
        words.pop()
    return " ".join(words).strip()


@dataclass(frozen=True)
class Dims:
    a: int | None = None
    b: int | None = None
    c: int | None = None


def parse_dims(text: str) -> Dims:
    """Parse NxN, N by N, N x N x N, N cubed, and lone sized adjectives nearby."""
    cubed = re.search(
        r"\b(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)\b",
        text,
        re.I,
    )
    if cubed:
        return Dims(int(cubed.group(1)), int(cubed.group(2)), int(cubed.group(3)))
    by3 = re.search(
        r"\b(\d+)\s+by\s+(\d+)\s+by\s+(\d+)\b",
        text,
        re.I,
    )
    if by3:
        return Dims(int(by3.group(1)), int(by3.group(2)), int(by3.group(3)))
    # Adult shorthand: "12 cubed" / "cube 8" → NxNxN
    n_cubed = re.search(r"\b(\d+)\s*cubed\b", text, re.I)
    if n_cubed:
        n = int(n_cubed.group(1))
        return Dims(n, n, n)
    cube_n = re.search(r"\bcube\s+(\d+)\b", text, re.I)
    if cube_n:
        n = int(cube_n.group(1))
        return Dims(n, n, n)
    pair = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\b", text, re.I)
    if pair:
        return Dims(int(pair.group(1)), int(pair.group(2)))
    by2 = re.search(r"\b(\d+)\s+by\s+(\d+)\b", text, re.I)
    if by2:
        return Dims(int(by2.group(1)), int(by2.group(2)))
    return Dims()


def parse_length_height(text: str) -> tuple[int | None, int | None]:
    """Parse length/height from NL size phrases.

    Shared-dimension forms with one number apply that number to both axes:
    ``20 wide and high``, ``20 wide and tall``, ``12 high and wide``,
    ``15 tall and long``.  This is distinct from ambiguous bare ``NxN`` walls.
    """
    length = None
    height = None
    # One number + both axis words → both dims equal that number.
    shared = re.search(
        r"\b(\d+)\s*(?:blocks?\s+)?"
        r"(?:"
        r"(?:(?:long|wide|across)\s+and\s+(?:high|tall))"
        r"|(?:(?:high|tall)\s+and\s+(?:long|wide|across))"
        r")\b",
        text,
        re.I,
    )
    if shared:
        n = int(shared.group(1))
        return n, n
    m = re.search(r"\b(\d+)\s*(?:blocks?\s+)?(?:long|wide|across)\b", text, re.I)
    if m:
        length = int(m.group(1))
    m = re.search(r"\b(\d+)\s*(?:blocks?\s+)?(?:high|tall)\b", text, re.I)
    if m:
        height = int(m.group(1))
    m = re.search(r"\b(?:height|tall|high)\s+(\d+)\b", text, re.I)
    if m and height is None:
        height = int(m.group(1))
    # "wide/long N and high/tall N" already covered by the two searches above
    # when both numbers are present ("20 wide and 10 high").
    return length, height


def looks_like_material_token(raw: str | None) -> bool:
    if not raw:
        return False
    token = raw.strip().lower()
    if not token or token in _BAD_MATERIALS:
        return False
    if re.fullmatch(r"\d+[x×]\d+(?:[x×]\d+)?", token):
        return False
    if re.fullmatch(r"\d+", token):
        return False
    if re.search(r"\d", token) and re.search(
        r"\b(?:high|tall|long|by|x)\b", token, re.I
    ):
        return False
    return True


_SHAPE_NOUNS = (
    r"wall|walls|platform|pad|deck|raft|box|tower|pillar|floor|floors|"
    r"blocks?|cylinder|cyl|room|shell|cube|enclosure|pen|yard|courtyard|"
    r"arena|compound|fence"
)


def _reject_dimensionish_material(candidate: str) -> bool:
    """True when a candidate looks like size/shape words, not a block."""
    token = candidate.strip().lower()
    if not token:
        return True
    if re.search(r"\d+\s*[x×]\s*\d+", token):
        return True
    if re.fullmatch(
        r"(?:a|an|the)\s+(?:square|rectangle|circle|area|footprint)",
        token,
    ):
        return True
    if token in {
        "square",
        "rectangle",
        "circle",
        "area",
        "footprint",
        "a square",
        "a rectangle",
        "an enclosure",
    }:
        return True
    return False


def extract_material_candidate(text: str) -> str | None:
    """Best-effort material phrase; caller must normalize."""
    m = re.search(
        rf"\b(?:with|using|in|of)\s+([a-z][a-z0-9 ]{{1,40}}?)"
        rf"(?=\s+(?:{_SHAPE_NOUNS})\b|[.!]|$)",
        text,
        re.I,
    )
    if m:
        candidate = _strip_material_trailing_noise(m.group(1))
        candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.I).strip()
        if looks_like_material_token(candidate) and not _reject_dimensionish_material(
            candidate
        ):
            return candidate
    m = re.search(
        r"\b((?:oak|spruce|birch|jungle|acacia|dark oak|cherry|mangrove|"
        r"stone|cobble|cobblestone|rock|rocks|rocky|brick|bricks|quartz|"
        r"glass|dirt|grass|gravel|sandstone|deepslate|nether|copper|prismarine|"
        r"wool|concrete|wood|wooden|dirt\s*path|grass\s*path)"
        r"(?:\s+(?:planks?|blocks?|bricks?|slab|stairs?|fence|path))?)\b",
        text,
        re.I,
    )
    if m:
        candidate = _strip_material_trailing_noise(m.group(1))
        if looks_like_material_token(candidate) and not _reject_dimensionish_material(
            candidate
        ):
            return candidate
    # Adjective before a shape noun: "rock wall", "neon platform".
    # Unknown tokens still surface so callers can refuse instead of held-item fallback.
    _loose_stop = _BAD_MATERIALS | {
        "build",
        "make",
        "place",
        "put",
        "create",
        "finish",
        "finsh",
        "complete",
        "fill",
        "between",
        "open",
        "remaining",
        "visible",
        "another",
        "please",
        "blocks",
        "block",
        "sized",
        "giant",
        "huge",
        "tiny",
        "free",
        "standing",
        "freestanding",
        "curtain",
        "around",
        "forming",
        "square",
        "rectangle",
    }
    m = re.search(
        rf"\b([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*){{0,2}})\s+(?:{_SHAPE_NOUNS})\b",
        text,
        re.I,
    )
    if m:
        candidate = _strip_material_trailing_noise(m.group(1))
        candidate = re.sub(r"^(?:a|an|the|my|me)\s+", "", candidate, flags=re.I).strip()
        words = [
            w
            for w in candidate.split()
            if w.lower() not in _loose_stop and not re.fullmatch(r"\d+", w)
        ]
        candidate = " ".join(words).strip()
        if looks_like_material_token(candidate) and not _reject_dimensionish_material(
            candidate
        ):
            return candidate
    return None


def is_enclosure_ask(text: str, dims: Dims | None = None) -> bool:
    """True for perimeter / multi-wall enclosure phrasing (not a single wall).

    Kid-facing examples: "4 walls in a 20x20 square", "wall me in 20x20",
    "rock enclosure 15 by 20", "surround with walls", "fence me in".
    Single-wall asks ("wall 20 long 5 high", bare "wall 20x20") stay False.
    """
    if dims is None:
        dims = parse_dims(text)
    has_footprint = dims.a is not None and dims.b is not None and dims.c is None
    has_any_size = has_footprint or any(
        v is not None for v in (*parse_length_height(text), dims.a, dims.b, dims.c)
    )

    # Curtain / freestanding single-wall jargon is never an enclosure.
    if re.search(r"\bcurtain\b", text, re.I):
        return False

    if re.search(
        r"\b(?:enclosure|courtyard|yard|arena|compound)\b",
        text,
        re.I,
    ):
        return True

    # Sized pen → parametric enclosure; unsized "sheep pen" stays template paste.
    if re.search(r"\bpens?\b", text, re.I) and has_any_size:
        return True

    if re.search(
        r"\b(?:wall|walls|box|fence)s?\s+me\s+in\b"
        r"|\bbox\s+me\s+in\b"
        r"|\bfence\s+me\s+in\b"
        r"|\bwall\s+me\s+in\b",
        text,
        re.I,
    ):
        return True

    if re.search(
        r"\bsurround(?:ed|ing)?(?:\s+me)?(?:\s+with)?\b",
        text,
        re.I,
    ) and re.search(r"\b(?:walls?|fence|fencing)\b", text, re.I):
        return True

    # Note: do not match "wall in front of me" (finish-wall phrasing).
    if re.search(
        r"\bwalls?\s+around\b"
        r"|\bwall\s+off\b"
        r"|\bwalls?\s+me\s+in\b"
        r"|\bwall(?:ed|ing)\s+(?:me\s+)?in\b",
        text,
        re.I,
    ):
        return True

    if re.search(
        r"\b(?:square|rectangle)\s+of\s+(?:[a-z]+\s+){0,3}(?:walls?|fencing|fences?)\b"
        r"|\b(?:walls?|fencing|fences?)\s+forming\b"
        r"|\b(?:walls?|fencing|fences?)\s+in\s+(?:an?\s+)?"
        r"(?:\d+\s*[x×]\s*\d+\s+|\d+\s+by\s+\d+\s+)?(?:square|rectangle)\b",
        text,
        re.I,
    ):
        return True

    # "4 rock walls … square/20x20" / "four walls in a square"
    multi = re.search(
        r"\b(?:\d+|two|three|four|five|six|seven|eight)\s+"
        r"(?:rock\s+|stone\s+|cobble(?:stone)?\s+|brick\s+|oak\s+)?"
        r"walls?\b",
        text,
        re.I,
    )
    if multi:
        count_raw = multi.group(0).split()[0].lower()
        count_map = {
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
        }
        count = count_map.get(count_raw, int(count_raw) if count_raw.isdigit() else 0)
        if count >= 3 and (
            has_footprint
            or re.search(r"\b(?:square|rectangle|enclosure)\b", text, re.I)
        ):
            return True

    return False


def wall_nxn_ambiguous(text: str, dims: Dims) -> bool:
    """True when wall + NxN lacks long/high disambiguators."""
    if dims.a is None or dims.b is None or dims.c is not None:
        return False
    if not re.search(r"\bwalls?\b", text, re.I):
        return False
    # Enclosure / perimeter phrasing is never the long-vs-square clarify.
    if is_enclosure_ask(text, dims):
        return False
    if re.search(r"\b(?:long|high|tall|wide|curtain|enclosure|square)\b", text, re.I):
        return False
    length, height = parse_length_height(text)
    return length is None and height is None


def over_budget_span(length: int, width: int) -> bool:
    """Bridge/road/path deck budget (matches PlaceShapeExecutor / BridgeSpan)."""
    return length > 1024 or width > 8 or length * width > 8192


def over_budget_platform(w: int, d: int) -> bool:
    return w * d > 1024 or w > 32 or d > 32


def over_budget_wall(length: int, height: int) -> bool:
    return length * height > 1536 or length > 48 or height > 32


def over_budget_box(w: int, d: int, h: int, *, roof: bool = True) -> bool:
    # outline upper bound rough: 2*(w*h + d*h) + optional roof
    outline = 2 * (w * h + d * h) + (w * d if roof else 0)
    return outline > 4000 or w > 32 or d > 32 or h > 24 or w < 3 or d < 3 or h < 2
