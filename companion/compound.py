"""Deterministic multi-action plans for compound kid requests."""

from __future__ import annotations

import re

from companion.routing import RouteDecision, route

_SPLIT = re.compile(
    r"\s*(?:,\s*then\s+|,\s+then\s+|,\s+and\s+|\s+and\s+then\s+|\s+then\s+|\s+and\s+)\s*",
    re.I,
)


def split_compound_prompt(prompt: str) -> list[str] | None:
    text = " ".join(prompt.strip().split())
    if not text:
        return None
    # Avoid splitting item phrases like "bread and butter" unless both sides
    # look like independent requests (verb-led or world-setting-led).
    parts = [part.strip(" .,!") for part in _SPLIT.split(text) if part.strip(" .,!")]
    if len(parts) < 2 or len(parts) > 3:
        return None
    return parts


def _looks_independent(part: str) -> bool:
    return bool(
        re.match(
            r"^(?:please\s+)?(?:"
            r"make|set|change|clear|give|spawn|summon|build|create|place|put|"
            r"finish|undo|let"
            r")\b",
            part,
            re.I,
        )
        or re.match(
            r"^(?:it\s+)?(?:day(?:time)?|night(?:time)?|noon|midnight|sunny|clear|rainy|rain)\b",
            part,
            re.I,
        )
    )


def route_compound(prompt: str, job_id: str) -> list[RouteDecision] | None:
    parts = split_compound_prompt(prompt)
    if parts is None:
        return None
    if not all(_looks_independent(part) for part in parts):
        # Soft repair: prefix bare weather/time tails.
        repaired: list[str] = []
        for part in parts:
            if _looks_independent(part):
                repaired.append(part)
            elif re.fullmatch(
                r"(?:day(?:time)?|night(?:time)?|noon|midnight)", part, re.I
            ):
                repaired.append(f"make it {part}")
            elif re.fullmatch(r"(?:clear|sunny|rain|rainy|thunder|stormy)", part, re.I):
                repaired.append(
                    "clear the weather"
                    if part.lower() in {"clear", "sunny"}
                    else f"make it {part}"
                )
            else:
                return None
        parts = repaired

    decisions: list[RouteDecision] = []
    for index, part in enumerate(parts):
        decision = route(part, f"{job_id}:c{index}")
        if decision.action is None:
            return None
        # Keep compound on deterministic/native tools only (no model).
        if decision.tier not in {"S", "A"}:
            return None
        decisions.append(decision)
    return decisions if len(decisions) >= 2 else None
