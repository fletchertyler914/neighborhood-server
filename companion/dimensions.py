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
    length = None
    height = None
    m = re.search(r"\b(\d+)\s*(?:blocks?\s+)?(?:long|wide|across)\b", text, re.I)
    if m:
        length = int(m.group(1))
    m = re.search(r"\b(\d+)\s*(?:blocks?\s+)?(?:high|tall)\b", text, re.I)
    if m:
        height = int(m.group(1))
    m = re.search(r"\b(?:height|tall|high)\s+(\d+)\b", text, re.I)
    if m and height is None:
        height = int(m.group(1))
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


def extract_material_candidate(text: str) -> str | None:
    """Best-effort material phrase; caller must normalize."""
    m = re.search(
        r"\b(?:with|using|in|of)\s+([a-z][a-z0-9 ]{1,40}?)"
        r"(?=\s+(?:wall|platform|pad|box|tower|floor|blocks?|cylinder|cyl|"
        r"room|shell|cube)\b|[.!]|$)",
        text,
        re.I,
    )
    if m:
        candidate = _strip_material_trailing_noise(m.group(1))
        if looks_like_material_token(candidate):
            return candidate
    m = re.search(
        r"\b((?:oak|spruce|birch|jungle|acacia|dark oak|cherry|mangrove|"
        r"stone|cobble|cobblestone|brick|bricks|quartz|glass|dirt|grass|"
        r"sandstone|deepslate|nether|copper|prismarine|wool|concrete)"
        r"(?:\s+[a-z]+){0,2})\b",
        text,
        re.I,
    )
    if m:
        candidate = _strip_material_trailing_noise(m.group(1))
        if looks_like_material_token(candidate):
            return candidate
    return None


def wall_nxn_ambiguous(text: str, dims: Dims) -> bool:
    """True when wall + NxN lacks long/high disambiguators."""
    if dims.a is None or dims.b is None or dims.c is not None:
        return False
    if not re.search(r"\bwalls?\b", text, re.I):
        return False
    if re.search(r"\b(?:long|high|tall|wide|curtain|enclosure|square)\b", text, re.I):
        return False
    length, height = parse_length_height(text)
    return length is None and height is None


def over_budget_platform(w: int, d: int) -> bool:
    return w * d > 1024 or w > 32 or d > 32


def over_budget_wall(length: int, height: int) -> bool:
    return length * height > 1536 or length > 48 or height > 32


def over_budget_box(w: int, d: int, h: int) -> bool:
    # outline upper bound rough: 2*(w*h + d*h) + roof
    outline = 2 * (w * h + d * h) + (w * d if True else 0)
    return outline > 4000 or w > 24 or d > 24 or h > 24 or w < 3 or d < 3 or h < 2
