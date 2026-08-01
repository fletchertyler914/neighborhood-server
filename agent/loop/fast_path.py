"""Deterministic high-confidence intents — no LLM."""

from __future__ import annotations

import re
from typing import Any

from agent.job import JobRequest


def try_fast_path(req: JobRequest) -> tuple[str, dict[str, Any]] | None:
    """Return (tool, args) if the prompt is unambiguous."""

    text = req.prompt.strip().lower()
    player = req.player

    # time
    m = re.search(
        r"\b(?:set\s+)?(?:the\s+)?time\s+(?:to\s+)?(day|night|noon|midnight|morning|dawn)\b",
        text,
    )
    if m:
        return "set_time", {"value": m.group(1)}
    if re.search(r"\bmake\s+it\s+day\b", text) or text in ("day", "set day"):
        return "set_time", {"value": "day"}
    if re.search(r"\bmake\s+it\s+night\b", text):
        return "set_time", {"value": "night"}

    # weather
    if re.search(r"\bmake\s+it\s+rain\b|\brain\b.*\bweather\b|\bweather\s+rain\b", text):
        return "set_weather", {"weather": "rain"}
    if re.search(r"\bclear\s+(?:the\s+)?(?:sky|weather)\b|\bmake\s+it\s+sunny\b|\bsunny\b", text):
        return "set_weather", {"weather": "clear"}
    if re.search(r"\bthunder\b|\bstorm\b", text) and "build" not in text:
        return "set_weather", {"weather": "thunder"}

    # give item (simple)
    m = re.search(
        r"\bgive\s+(?:me\s+)?(?:a\s+|an\s+)?([a-z0-9_ ]+?)(?:\s*$|\s+please)",
        text,
    )
    if m and "chicken" not in m.group(1) and "sheep" not in m.group(1):
        raw = m.group(1).strip()
        aliases = {
            "pickaxe": "diamond_pickaxe",
            "diamond pickaxe": "diamond_pickaxe",
            "diamond_pickaxe": "diamond_pickaxe",
            "sword": "diamond_sword",
            "dirt": "dirt",
            "dirt block": "dirt",
            "block of dirt": "dirt",
        }
        item = aliases.get(raw, aliases.get(raw.replace(" ", "_"), raw.replace(" ", "_")))
        return "give_item", {"player": player, "item": item, "count": 1}

    return None
