from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from companion.dimensions import looks_like_material_token, strip_politeness
from companion.models import Action
from companion.provider import CompiledIntent
from companion.templates import clarify_message, match_template

# "build X and clear everything in the way" / flatten / make room.
_CLEAR_SITE_RX = re.compile(
    r"\b(?:clear(?:ing)?|flatten|leve[l]?|bulldoze|terraform)\b.{"
    r"0,40}\b(?:way|path|space|spot|area|ground|terrain|everything|stuff|trees?|land)\b"
    r"|\b(?:clear|flatten|leve[l]?)\s+(?:everything|the\s+ground|the\s+land|a\s+pad|the\s+area)\b"
    r"|\b(?:make\s+room|clear\s+a\s+(?:spot|space|pad)|clear\s+out)\b"
    r"|\bclear\s+everything\s+in\s+the\s+way\b",
    re.I,
)
_FORWARD_BLOCKS_RX = re.compile(
    r"\b(\d{1,3})\s*blocks?\s+(?:in\s+front|ahead|forward)(?:\s+of\s+me)?\b",
    re.I,
)

# Must match SchematicPlacement.CLEAR_ASK_MESSAGE in the Paper plugin.
CLEAR_ASK_MESSAGE = (
    "I'll need to clear some ground there first — want me to? Try: yes"
)


def wants_clear_site(text: str) -> bool:
    """True when the player asks to clear/flatten terrain before a paste."""
    raw = text or ""
    # "clear a path/trail/road" is a corridor build, not paste site-clear.
    if re.search(
        r"\bclear\s+(?:a\s+)?(?:path|trail|road|footpath|walkway)\b",
        raw,
        re.I,
    ):
        return False
    return bool(_CLEAR_SITE_RX.search(raw))


def extract_forward_blocks(text: str) -> int | None:
    """Optional 'N blocks in front' distance for near-edge placement."""
    match = _FORWARD_BLOCKS_RX.search(text or "")
    if match is None:
        return None
    value = int(match.group(1))
    if 1 <= value <= 128:
        return value
    return None


def is_clear_ask_message(message: str) -> bool:
    text = (message or "").strip()
    return text.startswith("I'll need to clear some ground") or CLEAR_ASK_MESSAGE in text


def _paste_template_args(template_id: str, prompt: str = "") -> dict[str, Any]:
    """Args for curated paste_template.

    Always opt into ``clear_site``: saying “build X” / picking from the Build Book
    already means place it here. The old ask-every-time “Try: yes” loop was too
    heavy for kids (and broke mega pastes on the follow-up job budget).
    """
    args: dict[str, Any] = {"template_id": template_id, "clear_site": True}
    forward = extract_forward_blocks(prompt)
    if forward is not None:
        args["forward_blocks"] = forward
    return args


@dataclass(frozen=True)
class RouteDecision:
    route: str
    tier: str
    action: Action | None = None
    message: str = ""
    pending_kind: str = ""
    pending_slots: dict[str, Any] | None = None


_TIME_PATTERNS = (
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?time\s+(?:to\s+)?day(?:time)?[.!]?$", re.I), "day"),
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?time\s+(?:to\s+)?noon[.!]?$", re.I), "noon"),
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?time\s+(?:to\s+)?night(?:time)?[.!]?$", re.I), "night"),
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?time\s+(?:to\s+)?midnight[.!]?$", re.I), "midnight"),
    (re.compile(r"^(?:make\s+it|let\s+it\s+be)\s+day(?:time)?[.!]?$", re.I), "day"),
    (re.compile(r"^(?:make\s+it|let\s+it\s+be)\s+noon[.!]?$", re.I), "noon"),
    (re.compile(r"^(?:make\s+it|let\s+it\s+be)\s+night(?:time)?[.!]?$", re.I), "night"),
    (re.compile(r"^(?:make\s+it|let\s+it\s+be)\s+midnight[.!]?$", re.I), "midnight"),
)

_WEATHER_PATTERNS = (
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?weather\s+(?:to\s+)?(?:clear|sunny)[.!]?$", re.I), "clear"),
    (re.compile(r"^(?:please\s+)?(?:clear|stop)\s+(?:the\s+)?weather[.!]?$", re.I), "clear"),
    (re.compile(r"^(?:please\s+)?(?:set|make)\s+it\s+(?:clear|sunny)[.!]?$", re.I), "clear"),
    (re.compile(r"^(?:please\s+)?make\s+it\s+(?:rain|rainy)[.!]?$", re.I), "rain"),
    (re.compile(r"^(?:please\s+)?make\s+it\s+(?:storm|stormy|thunder)[.!]?$", re.I), "thunder"),
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?weather\s+(?:to\s+)?(?:rain|rainy)[.!]?$", re.I), "rain"),
    (re.compile(r"^(?:please\s+)?(?:set|make|change)\s+(?:the\s+)?weather\s+(?:to\s+)?(?:thunder|storm|stormy)[.!]?$", re.I), "thunder"),
)

_ITEM_ALIASES = {
    "dirt block": "dirt",
    "dirt blocks": "dirt",
    "block of dirt": "dirt",
    "grass block": "grass_block",
    "wood": "oak_log",
    "wooden planks": "oak_planks",
    "planks": "oak_planks",
    "torch": "torch",
    "torches": "torch",
    "diamond": "diamond",
    "diamonds": "diamond",
    "iron ingot": "iron_ingot",
    "iron ingots": "iron_ingot",
}

_ENTITY_ALIASES = {
    "chicken": "chicken",
    "chickens": "chicken",
    "cow": "cow",
    "cows": "cow",
    "pig": "pig",
    "pigs": "pig",
    "sheep": "sheep",
    "horse": "horse",
    "horses": "horse",
    "wolf": "wolf",
    "wolves": "wolf",
    "creeper": "creeper",
    "creepers": "creeper",
    "zombie": "zombie",
    "zombies": "zombie",
    "skeleton": "skeleton",
    "skeletons": "skeleton",
    "blaze": "blaze",
    "blazes": "blaze",
    "enderman": "enderman",
    "endermen": "enderman",
    "wither": "wither",
    "withers": "wither",
    "warden": "warden",
    "wardens": "warden",
    "ghast": "ghast",
    "ghasts": "ghast",
    "phantom": "phantom",
    "phantoms": "phantom",
    "ravager": "ravager",
    "ravagers": "ravager",
    "ender dragon": "ender_dragon",
    "enderdragon": "ender_dragon",
    "ender_dragon": "ender_dragon",
    "dragon": "ender_dragon",
    "elder guardian": "elder_guardian",
    "elder_guardian": "elder_guardian",
}

# Admin / server-integrity items only — not "scary" gameplay items like TNT.
_REFUSED_ITEMS = {
    "command block",
    "command_block",
    "chain command block",
    "chain_command_block",
    "repeating command block",
    "repeating_command_block",
    "structure block",
    "structure_block",
    "jigsaw",
    "debug stick",
    "debug_stick",
}

_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "tree": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

# Deictic give: "give me these/those/that/this (blocks)" — native gaze, not named items.
_GAZE_GIVE_RX = re.compile(
    r"(?:please\s+)?"
    r"(?:give\s+me|gimme|can i (?:have|get)|i want)"
    r"\s+"
    r"(?:"
    r"(?:a\s+)?stack\s+of\s+"
    r"|(\d+|a|an|one|two|three|tree|four|five|six|seven|eight|nine|ten|some)\s+"
    r")?"
    r"(?:of\s+)?"
    r"(?:these|those|that|this)"
    r"(?:\s+blocks?)?"
    r"[.!]?",
    re.I,
)


_MATERIAL_ALIASES = {
    "quartz": "quartz_block",
    "quart": "quartz_block",
    "quartz block": "quartz_block",
    "smooth quartz": "smooth_quartz",
    "oak": "oak_planks",
    "oak planks": "oak_planks",
    "wood": "oak_planks",
    "wooden": "oak_planks",
    "stone": "stone",
    "cobble": "cobblestone",
    "cobblestone": "cobblestone",
    # NL "rock wall" → solid masonry (cobble matches seed/catalog convention).
    "rock": "cobblestone",
    "rocks": "cobblestone",
    "rocky": "cobblestone",
    "glass": "glass",
    "brick": "bricks",
    "bricks": "bricks",
    "fence": "oak_fence",
    "fencing": "oak_fence",
    "oak fence": "oak_fence",
    "wooden fence": "oak_fence",
    "dirt path": "dirt_path",
    "dirt_path": "dirt_path",
    "grass path": "dirt_path",
    "grass_path": "dirt_path",
    "path block": "dirt_path",
    "gravel": "gravel",
    "dirt": "dirt",
}

# Story adjectives — never treat these as block materials.
_FLOOR_STORY = (
    r"(?:second|2nd|third|3rd|fourth|4th|next|upper|top|first|1st)"
)
_FLOOR_NOUN = r"(?:floor|story|storey)"
# Optional "for/on my castle" etc. — contextual, not a template paste.
_FLOOR_CONTEXT = (
    r"(?:\s+(?:for|on|in|onto|inside|of)\s+(?:(?:my|the|this|a)\s+)?"
    r"[a-z][a-z0-9 ]{0,40})?"
)


_MATERIAL_SHAPE_SUFFIXES = (
    "_wall",
    "_walls",
    "_platform",
    "_pad",
    "_deck",
    "_raft",
    "_box",
    "_room",
    "_shell",
    "_cube",
    "_tower",
    "_pillar",
    "_cylinder",
    "_cyl",
    "_floor",
    "_floors",
    "_radius",
    "_height",
    "_enclosure",
    "_pen",
    "_yard",
    "_courtyard",
    "_arena",
    "_compound",
    "_fence",
    "_square",
    "_rectangle",
)


def _normalize_material(raw: str) -> str | None:
    from companion.dimensions import _strip_material_trailing_noise

    text = " ".join(raw.lower().strip().split())
    text = _strip_material_trailing_noise(text)
    if not text or re.fullmatch(_FLOOR_STORY, text, re.I):
        return None

    def resolve(phrase: str) -> str | None:
        if not phrase:
            return None
        if phrase in _MATERIAL_ALIASES:
            return _MATERIAL_ALIASES[phrase]
        words = phrase.split()
        for end in range(len(words), 0, -1):
            prefix = " ".join(words[:end])
            if prefix in _MATERIAL_ALIASES:
                return _MATERIAL_ALIASES[prefix]
        candidate = phrase.replace(" ", "_")
        if re.fullmatch(r"[a-z0-9_]+", candidate):
            return candidate
        return None

    # Peel shape suffixes off underscored junk before resolving
    # ("oak_platform" → "oak", "quartz_cylinder_radius" → "quartz").
    underscored = text.replace(" ", "_")
    trimmed = underscored
    while True:
        peeled = False
        for suffix in _MATERIAL_SHAPE_SUFFIXES:
            if trimmed.endswith(suffix) and len(trimmed) > len(suffix):
                trimmed = trimmed[: -len(suffix)]
                peeled = True
                break
        if not peeled:
            break
    for phrase in (text, trimmed.replace("_", " "), trimmed):
        hit = resolve(phrase)
        if hit is not None and not any(
            hit.endswith(suffix) for suffix in _MATERIAL_SHAPE_SUFFIXES
        ):
            return hit
        if hit is not None and hit in _MATERIAL_ALIASES.values():
            return hit
    return resolve(text)


def _is_upper_floor_intent(text: str) -> bool:
    """True when the ask is to add/finish an upper story, not paste a building."""
    return bool(
        re.search(
            rf"\b(?:build|make|add|put|finish|finsh|complete|fill\s+in)\b"
            rf".*\b{_FLOOR_STORY}\s+{_FLOOR_NOUN}\b",
            text,
            re.I,
        )
        or re.search(
            rf"\b(?:finish|finsh|complete|fill\s+in)\b.*\bupstairs\b",
            text,
            re.I,
        )
        or re.search(
            rf"\b(?:build|make|add)\b.*\bupstairs\s+{_FLOOR_NOUN}\b",
            text,
            re.I,
        )
    )


def _route_finish_floor(text: str, job_id: str) -> RouteDecision | None:
    # Upper story / second floor: perception fill, never another schematic paste.
    upper = re.fullmatch(
        rf"(?:please\s+)?"
        rf"(?:(?:build|make|add|put)\s+(?:(?:me\s+)?(?:a|an|the|another)\s+)?|"
        rf"(?:finish|finsh|complete|fill\s+in)\s+(?:(?:this|the|a|an|my)\s+)?)"
        rf"{_FLOOR_STORY}\s+{_FLOOR_NOUN}"
        rf"{_FLOOR_CONTEXT}"
        rf"(?:\s+(?:with|using)\s+(?P<material>[a-z][a-z0-9 ]{{0,40}}))?"
        rf"[.!]?",
        text,
        re.I,
    )
    if not upper:
        upper = re.fullmatch(
            rf"(?:please\s+)?"
            rf"(?:build|make|add|finish|finsh|complete)\s+"
            rf"(?:(?:me\s+)?(?:a|an|the)\s+)?"
            rf"upstairs(?:\s+{_FLOOR_NOUN})?"
            rf"{_FLOOR_CONTEXT}"
            rf"(?:\s+(?:with|using)\s+(?P<material>[a-z][a-z0-9 ]{{0,40}}))?"
            rf"[.!]?",
            text,
            re.I,
        )
    if upper or _is_upper_floor_intent(text):
        args: dict[str, Any] = {"mode": "fill"}
        material_raw = upper.groupdict().get("material") if upper else None
        if material_raw:
            material = _normalize_material(material_raw)
            if material is None:
                return RouteDecision(
                    route="grammar.clarify_floor_material",
                    tier="S",
                    message="What block should I use? Try: finish this floor with glass",
                )
            args["material"] = material
        return RouteDecision(
            route="pattern.finish_floor_upper",
            tier="A",
            action=_action(job_id, "finish_floor", args, risk="bounded"),
        )

    # Clear / empty the sensed room floor plane.
    clear = re.fullmatch(
        r"(?:please\s+)?(?:clear|empty|remove)\s+"
        r"(?:(?:this|the|a)\s+)?"
        r"(?:floor|ground)"
        r"(?:\s+(?:in\s+(?:this\s+)?room|here|under\s+me))?"
        r"[.!]?",
        text,
        re.I,
    )
    if clear:
        return RouteDecision(
            route="pattern.finish_floor_clear",
            tier="A",
            action=_action(job_id, "finish_floor", {"mode": "clear"}, risk="bounded"),
        )

    # Convert / replace an existing floor material.
    # Accepts: "make this floor oak planks", "change the floor to glass".
    replace = re.fullmatch(
        r"(?:please\s+)?(?:make|change|convert|turn|set)\s+"
        r"(?:(?:this|the|a)\s+)?"
        r"(?:floor|ground)"
        r"(?:\s+(?:in\s+(?:this\s+)?room|here))?"
        r"\s+(?:(?:to|into|with|using)\s+)?(?P<material>[a-z][a-z0-9 ]{0,40})"
        r"[.!]?",
        text,
        re.I,
    )
    if not replace:
        replace = re.fullmatch(
            r"(?:please\s+)?(?:floor|pave)\s+"
            r"(?:(?:this|the)\s+)?(?:room|floor|ground)?\s+"
            r"(?:in|with|using)\s+(?P<material>[a-z][a-z0-9 ]{0,40})"
            r"[.!]?",
            text,
            re.I,
        )
    if replace:
        material = _normalize_material(replace.group("material"))
        if material is None:
            return RouteDecision(
                route="grammar.clarify_floor_material",
                tier="S",
                message="What block should I use? Try: make this floor glass",
            )
        return RouteDecision(
            route="pattern.finish_floor_replace",
            tier="A",
            action=_action(
                job_id,
                "finish_floor",
                {"mode": "replace", "material": material},
                risk="bounded",
            ),
        )

    # Default fill: finish / complete / fill in air cells.
    # Story adjectives are part of the floor phrase, not materials.
    match = re.fullmatch(
        r"(?:please\s+)?(?:finish|finsh|complete|fill\s+in)\s+"
        r"(?:(?:this|the|a)\s+)?"
        rf"(?:(?P<story>{_FLOOR_STORY})\s+)?"
        r"(?:(?P<material>[a-z][a-z0-9 ]{0,40}?)\s+)?"
        r"(?:floor|ground)"
        r"(?:\s+(?:in\s+(?:this\s+)?room|here|under\s+me))?"
        r"(?:\s+(?:with|using|in)\s+(?P<material2>[a-z][a-z0-9 ]{0,40}))?"
        r"[.!]?",
        text,
        re.I,
    )
    if not match:
        match = re.fullmatch(
            r"(?:please\s+)?(?:floor|pave)\s+"
            r"(?:(?:this|the)\s+)?(?:room|floor|ground)?"
            r"(?:\s+(?:with|using)\s+(?P<material2>[a-z][a-z0-9 ]{0,40}))?"
            r"[.!]?",
            text,
            re.I,
        )
    if not match:
        return None
    args = {"mode": "fill"}
    material_raw = match.groupdict().get("material2") or match.groupdict().get("material")
    if material_raw and not re.fullmatch(_FLOOR_STORY, material_raw.strip(), re.I):
        material = _normalize_material(material_raw)
        if material is None:
            return RouteDecision(
                route="grammar.clarify_floor_material",
                tier="S",
                message="What block should I use? Try: finish this floor with glass",
            )
        args["material"] = material
    return RouteDecision(
        route="pattern.finish_floor",
        tier="A",
        action=_action(job_id, "finish_floor", args, risk="bounded"),
    )


def _route_finish_wall(text: str, job_id: str) -> RouteDecision | None:
    # Typos + optional material + optional height.
    match = re.fullmatch(
        r"(?:please\s+)?(?:finish|finsh|complete|fill\s+in)\s+"
        r"(?:(?:this|the|a)\s+)?"
        r"(?:(?P<material>[a-z][a-z0-9 ]{0,40}?)\s+)?"
        r"walls?"
        r"(?:\s+(?:in\s+front\s+of\s+me|here|between(?:\s+the\s+\w+)?))?"
        r"(?:\s+(?:with|using|in)\s+(?P<material2>[a-z][a-z0-9 ]{0,40}))?"
        r"(?:\s+(?:and\s+)?(?:make\s+it\s+)?"
        r"(?P<height>\d+)\s+blocks?\s+(?:high|tall))?"
        r"[.!]?",
        text,
        re.I,
    )
    if not match:
        # "build a quartz wall between the oak planks" — contextual only.
        match = re.fullmatch(
            r"(?:please\s+)?(?:build|make|put)\s+(?:a\s+|me\s+a\s+)?"
            r"(?P<material>[a-z][a-z0-9 ]{0,40}?)\s+walls?"
            r"(?:\s+between(?:\s+the\s+\w+(?:\s+\w+)*)+)"
            r"(?:\s+(?P<height>\d+)\s+blocks?\s+(?:high|tall))?"
            r"[.!]?",
            text,
            re.I,
        )
    if not match:
        # Material wall without size → finish open wall (held/named material).
        match = re.fullmatch(
            r"(?:please\s+)?(?:build|make|put)\s+(?:a\s+|me\s+a\s+)?"
            r"(?P<material>[a-z][a-z0-9 ]{0,40}?)\s+walls?"
            r"(?:\s+(?:here|in\s+front(?:\s+of\s+me)?))?"
            r"[.!]?",
            text,
            re.I,
        )
        if match and (
            re.search(r"\d", match.group("material") or "")
            or not looks_like_material_token(match.group("material"))
        ):
            return None
    if not match:
        return None
    args: dict[str, Any] = {}
    height_raw = match.groupdict().get("height")
    if height_raw:
        height = int(height_raw)
        if not 2 <= height <= 128:
            return RouteDecision(
                route="grammar.clarify_wall_height",
                tier="S",
                message="How tall should it be? Try: finish this wall 12 blocks high",
            )
        args["height"] = height
    material_raw = match.groupdict().get("material2") or match.groupdict().get("material")
    if material_raw:
        if not looks_like_material_token(material_raw):
            material_raw = None
        else:
            material = _normalize_material(material_raw)
            if material is None:
                return RouteDecision(
                    route="grammar.clarify_wall_material",
                    tier="S",
                    message="What block should I use? Try: finish this wall with quartz",
                )
            args["material"] = material
    return RouteDecision(
        route="pattern.finish_wall",
        tier="A",
        action=_action(job_id, "finish_wall", args, risk="bounded"),
    )


def _action(job_id: str, tool: str, arguments: dict[str, Any], risk: str = "safe") -> Action:
    canonical = f"{job_id}:{tool}:{sorted(arguments.items())}"
    key = hashlib.sha256(canonical.encode()).hexdigest()
    return Action(
        tool=tool,
        arguments=arguments,
        idempotency_key=key,
        risk=risk,
    )


def route(
    prompt: str,
    job_id: str,
    *,
    capabilities: set[str] | None = None,
    has_finishable_wall: bool = False,
    can_ingest: bool = False,
) -> RouteDecision:
    text = strip_politeness(" ".join(prompt.strip().split()))
    from companion.help import route_help
    from companion.ingest_routing import route_ingest
    from companion.place_routing import route_place_shape

    help_decision = route_help(text)
    if help_decision is not None:
        return help_decision

    ingest_decision = route_ingest(text, can_ingest=can_ingest)
    if ingest_decision is not None:
        return ingest_decision

    has_place_shape = capabilities is None or "place_shape" in capabilities
    has_mark_route = capabilities is None or "mark_route" in capabilities
    place_decision = route_place_shape(
        text,
        job_id,
        has_place_shape=has_place_shape,
        has_finishable_wall=has_finishable_wall,
        has_mark_route=has_mark_route,
    )
    if place_decision is not None:
        return place_decision
    if re.search(r"\b(?:give|can i have|i want)\b", text, re.I) and any(
        re.search(rf"\b{re.escape(item)}\b", text, re.I) for item in _REFUSED_ITEMS
    ):
        return RouteDecision(
            route="policy.refuse_restricted_item",
            tier="S",
            message="I can't give out admin blocks. Try: stone, glass, or oak planks.",
        )
    if re.fullmatch(
        r"(?:please\s+)?(?:undo(?:\s+that)?|put\s+it\s+back|take\s+that\s+back)[.!]?",
        text,
        re.I,
    ):
        return RouteDecision(
            route="grammar.undo_last",
            tier="S",
            action=_action(job_id, "undo_last", {}),
        )
    # Cancel pending clarify — not the same as undoing a world edit.
    if re.fullmatch(
        r"(?:please\s+)?(?:nevermind|never\s+mind|cancel|forget\s+it|stop)[.!]?",
        text,
        re.I,
    ):
        return RouteDecision(
            route="grammar.cancel",
            tier="S",
            message="Okay, never mind.",
            pending_kind="__cancel__",
        )
    floor_decision = _route_finish_floor(text, job_id)
    if floor_decision is not None:
        return floor_decision
    wall_decision = _route_finish_wall(text, job_id)
    if wall_decision is not None:
        return wall_decision
    vague_build = re.fullmatch(
        r"(?:please\s+)?(?:build|make)(?:\s+me)?\s+(?:a\s+)?(?:house|home|building|place)[.!]?",
        text,
        re.I,
    )
    if vague_build:
        return RouteDecision(
            route="grammar.clarify_build",
            tier="S",
            message="What kind of place? Try chicken coop, cottage, market stall, or bridge.",
            pending_kind="template",
            pending_slots={
                "default_tool": "paste_template",
                "default_arguments": {"template_id": "cottage_medium"},
            },
        )

    build_verb = bool(
        re.search(
            r"\b(?:build|make|create|construct|place|put|plant|grow|sow)\b",
            text,
            re.I,
        )
    )
    structure_noun = bool(
        re.search(
            r"\b(?:house|home|coop|pen|castle|bridge|watchtower|cottage|barn|"
            r"tower|well|apiary|garden|farm|greenhouse|orchard|crop|crops|"
            r"farmland|allotment|flower|flowers|flowerbed|patch|bed|"
            r"carrot|potato|berry|berries|wheat|pumpkin|melon|herb|herbs|"
            r"veggie|vegetable|combo|mixed|market|stall|shop|store|vendor|"
            r"booth|stand|bakery|blacksmith|igloo|lighthouse|windmill|"
            r"gazebo|pier|dock|plaza|cabin|tavern|inn|library|church|"
            r"cathedral|gothic|mansion|manor|spruce|"
            r"apartment|treehouse|stable|hutch|silo|workshop|warehouse)\b",
            text,
            re.I,
        )
    )
    # Hybrid ranker may recognize bare noun phrases ("market stall") even
    # when the keyword list is incomplete — try whenever this is not a
    # clear give/summon/world command.
    # "clear" alone is often finish_floor / refuse — but "build X and clear
    # everything" is still a paste. Exclude clear-site phrasing here.
    non_build_command = bool(
        re.search(
            r"\b(?:spawn|summon|give|set|change|undo|cancel)\b",
            text,
            re.I,
        )
    ) or (
        bool(re.search(r"\bclear\b", text, re.I))
        and not build_verb
        and not wants_clear_site(text)
    )
    template_candidate = None
    if build_verb or (structure_noun and not non_build_command) or (
        not non_build_command and len(text.split()) <= 6
    ):
        template_candidate = match_template(text, gold_only=True)

    if build_verb or (
        structure_noun and not non_build_command and template_candidate is not None
    ) or (
        not non_build_command
        and template_candidate is not None
        and (
            template_candidate.confidence == "high"
            or (
                template_candidate.gold
                and not template_candidate.needs_clarify
                and template_candidate.score >= 0.72
            )
        )
    ):
        if re.search(r"\b(?:move|shift|rotate)\b", text, re.I) and re.search(
            r"\b(?:add|change|paint|replace)\b", text, re.I
        ):
            return RouteDecision(
                route="grammar.clarify_complex_build",
                tier="S",
                message="Let's do one thing at a time. What should I build first?",
            )
        # Never let wall-completion phrasing fall into wall_segment templates.
        if re.search(r"\bwalls?\b", text, re.I) and re.search(
            r"\b(?:finish|finsh|complete|fill|between|remaining|open)\b", text, re.I
        ):
            wall = _route_finish_wall(text, job_id)
            if wall is not None:
                return wall
        # Upper-story asks must not paste another building just because
        # "castle"/"house" appears in "second floor for my castle".
        if _is_upper_floor_intent(text):
            floor = _route_finish_floor(text, job_id)
            if floor is not None:
                return floor
            return RouteDecision(
                route="pattern.finish_floor_upper",
                tier="A",
                action=_action(
                    job_id, "finish_floor", {"mode": "fill"}, risk="bounded"
                ),
            )
        template = template_candidate or match_template(text, gold_only=True)
        if template is not None and str(template.template_id).startswith("wall_segment"):
            return RouteDecision(
                route="grammar.clarify_wall",
                tier="S",
                message="Look at a corner of the open wall and try: finish this wall",
            )
        if template is not None and not template.gold:
            return RouteDecision(
                route="grammar.clarify_gold_template",
                tier="S",
                message=(
                    "I don't have a great build for that yet. "
                    "Try: little castle, chicken house, or bridge."
                ),
            )
        if (
            template is not None
            and template.needs_clarify
            and (structure_noun or template.confidence in {"high", "medium"})
            and template.score >= 0.45
        ):
            return RouteDecision(
                route="grammar.clarify_template",
                tier="S",
                message=clarify_message(template),
                pending_kind="template",
                pending_slots={
                    "default_tool": "paste_template",
                    "default_arguments": {"template_id": template.template_id},
                    "candidates": list(template.alternatives),
                },
            )
        if template is not None and template.gold and not template.needs_clarify:
            return RouteDecision(
                route="ranker.paste_template",
                tier="A",
                action=_action(
                    job_id,
                    "paste_template",
                    _paste_template_args(template.template_id, text),
                    risk="bounded",
                ),
            )
    for pattern, value in _TIME_PATTERNS:
        if pattern.fullmatch(text):
            return RouteDecision(
                route="grammar.set_time",
                tier="S",
                action=_action(job_id, "set_time", {"time": value}),
            )
    for pattern, value in _WEATHER_PATTERNS:
        if pattern.fullmatch(text):
            return RouteDecision(
                route="grammar.set_weather",
                tier="S",
                action=_action(job_id, "set_weather", {"weather": value}),
            )

    few_mobs = re.search(
        r"\bgive\s+me\s+(?:a\s+)?few\s+(chickens?|cows?|pigs?|sheep|horses?|wolves?)\b",
        text,
        re.I,
    )
    if few_mobs:
        entity = _ENTITY_ALIASES.get(few_mobs.group(1).lower())
        if entity:
            return RouteDecision(
                route="grammar.summon_entity",
                tier="A",
                action=_action(
                    job_id,
                    "summon_entity",
                    {"entity": entity, "count": 3},
                    risk="bounded",
                ),
            )

    gaze_give = _GAZE_GIVE_RX.fullmatch(text)
    if gaze_give:
        count_token = (gaze_give.group(1) or "").lower()
        if count_token == "some" or not count_token:
            amount = 64
        elif count_token.isdigit():
            amount = int(count_token)
        else:
            amount = _NUMBER_WORDS.get(count_token, 64)
        # "a/an/one of these" → 1; bare "these blocks" / "some" → a stack.
        if "stack" in text.lower():
            amount = 64
        if 1 <= amount <= 64:
            args: dict[str, Any] = {}
            if amount != 64:
                args["amount"] = amount
            return RouteDecision(
                route="grammar.give_looked_item",
                tier="S",
                action=_action(job_id, "give_looked_item", args),
            )

    give_match = re.fullmatch(
        r"(?:please\s+)?give\s+me\s+(?:(\d+|a|an|one|two|three|tree|four|five|six|seven|eight|nine|ten)\s+)?(.+?)[.!]?",
        text,
        re.I,
    )
    if give_match:
        count_token = (give_match.group(1) or "one").lower()
        amount = int(count_token) if count_token.isdigit() else _NUMBER_WORDS[count_token]
        raw_item = give_match.group(2).lower().strip()
        few_entity = re.fullmatch(r"(?:a\s+)?few\s+(.+)", raw_item)
        if few_entity:
            entity = _ENTITY_ALIASES.get(few_entity.group(1))
            if entity:
                return RouteDecision(
                    route="grammar.summon_entity",
                    tier="A",
                    action=_action(
                        job_id,
                        "summon_entity",
                        {"entity": entity, "count": 3},
                        risk="bounded",
                    ),
                )
        stack_item = re.fullmatch(r"(?:a\s+)?stack\s+of\s+(.+)", raw_item)
        if stack_item:
            amount = 64
            raw_item = stack_item.group(1)
        some_item = re.fullmatch(r"some\s+(.+)", raw_item)
        if some_item:
            raw_item = some_item.group(1)
        material = _ITEM_ALIASES.get(raw_item, raw_item.replace(" ", "_"))
        if re.fullmatch(r"[a-z0-9_]+", material) and 1 <= amount <= 64:
            return RouteDecision(
                route="grammar.give_item",
                tier="S",
                action=_action(
                    job_id,
                    "give_item",
                    {"material": material, "amount": amount},
                ),
            )

    summon_match = re.fullmatch(
        r"(?:please\s+)?(summon|spawn|make)\s+(?:(\d+|a|an|one|two|three|tree|four|five|six|seven|eight|nine|ten)\s+)?(.+?)(?:\s+(?:here|near me|by me))?[.!]?",
        text,
        re.I,
    )
    if summon_match:
        verb = summon_match.group(1).lower()
        count_token = (summon_match.group(2) or "one").lower()
        count = int(count_token) if count_token.isdigit() else _NUMBER_WORDS[count_token]
        raw_entity = summon_match.group(3).lower().strip()
        entity = _ENTITY_ALIASES.get(raw_entity)
        # Free-form mob ids only for explicit summon/spawn — "make it bigger"
        # must not become summon_entity("it_bigger").
        if entity is None and verb in {"summon", "spawn"}:
            candidate = raw_entity.replace("-", "_")
            if " " not in raw_entity and re.fullmatch(
                r"[a-z][a-z0-9_]{1,62}", candidate
            ):
                entity = candidate
        if entity and 1 <= count <= 20:
            return RouteDecision(
                route="grammar.summon_entity",
                tier="A",
                action=_action(
                    job_id,
                    "summon_entity",
                    {"entity": entity, "count": count},
                    risk="bounded",
                ),
            )

    want_give = re.fullmatch(
        r"(?:please\s+)?(?:can i (?:have|get)|i want)\s+(?:some\s+)?(.+?)[.!]?",
        text,
        re.I,
    )
    if want_give:
        raw_item = want_give.group(1).lower().strip()
        raw_item = re.sub(r"^(?:a|an)\s+", "", raw_item)
        # "can i get a market stall" is a build ask, not an item give.
        build_ask = match_template(raw_item, gold_only=True)
        if (
            build_ask is not None
            and build_ask.gold
            and not build_ask.needs_clarify
            and build_ask.confidence == "high"
            and build_ask.score >= 0.9
        ):
            return RouteDecision(
                route="ranker.paste_template",
                tier="A",
                action=_action(
                    job_id,
                    "paste_template",
                    _paste_template_args(build_ask.template_id, text),
                    risk="bounded",
                ),
            )
        material = _ITEM_ALIASES.get(raw_item, raw_item.replace(" ", "_"))
        if re.fullmatch(r"[a-z0-9_]+", material):
            readable = material.replace("_", " ")
            if not readable.endswith("s"):
                readable = readable + "s"
            return RouteDecision(
                route="grammar.clarify_give",
                tier="S",
                message=f"How many {readable} do you want? Say a number from 1 to 64.",
                pending_kind="give",
                pending_slots={"material": material},
            )

    return RouteDecision(
        route="unresolved",
        tier="B",
        message="I’m not sure yet. Try: make it daytime",
    )


def compiled_route(
    intent: CompiledIntent, job_id: str, prompt: str = ""
) -> RouteDecision:
    if intent.kind != "action" or intent.tool is None:
        message = intent.message.strip()[:160]
        return RouteDecision(
            route=f"model.{intent.kind}",
            tier="B",
            message=message or "Could you say that another way?",
        )
    arguments = dict(intent.arguments)
    if intent.tool == "set_time":
        if arguments.get("time") not in {"day", "noon", "night", "midnight"}:
            return _invalid_model_route()
    elif intent.tool == "set_weather":
        if arguments.get("weather") not in {"clear", "rain", "thunder"}:
            return _invalid_model_route()
    elif intent.tool == "give_item":
        material = arguments.get("material")
        amount = arguments.get("amount")
        if (
            not isinstance(material, str)
            or re.fullmatch(r"[a-z0-9_]+", material) is None
            or not isinstance(amount, int)
            or isinstance(amount, bool)
            or not 1 <= amount <= 64
        ):
            return _invalid_model_route()
    elif intent.tool == "give_looked_item":
        cleaned_gaze: dict[str, Any] = {}
        if "amount" in arguments and arguments.get("amount") is not None:
            amount = arguments.get("amount")
            if (
                not isinstance(amount, int)
                or isinstance(amount, bool)
                or not 1 <= amount <= 64
            ):
                return _invalid_model_route()
            cleaned_gaze["amount"] = amount
        arguments = cleaned_gaze
    elif intent.tool == "summon_entity":
        entity = arguments.get("entity")
        count = arguments.get("count")
        if isinstance(entity, str):
            entity = _ENTITY_ALIASES.get(
                entity.lower(), entity.lower().replace(" ", "_").replace("-", "_")
            )
            arguments = {**arguments, "entity": entity}
        if (
            not isinstance(entity, str)
            or re.fullmatch(r"[a-z0-9_]+", entity) is None
            or not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= 20
        ):
            return _invalid_model_route()
    elif intent.tool == "paste_template":
        template_id = arguments.get("template_id")
        if (
            not isinstance(template_id, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", template_id) is None
        ):
            return _invalid_model_route()
        clear_site = arguments.get("clear_site") is True or wants_clear_site(prompt)
        # Prefer NL ranker on the player prompt over a model-invented id
        # (stops cmapground→carrot_farm style category steals).
        ranked = match_template(prompt, gold_only=True)
        if ranked is None:
            ranked = match_template(template_id.replace("_", " "), gold_only=True)
        if ranked is not None and ranked.gold and not ranked.needs_clarify:
            arguments = {"template_id": ranked.template_id}
            if clear_site:
                arguments["clear_site"] = True
        elif ranked is not None and ranked.needs_clarify:
            return RouteDecision(
                route="model.clarify",
                tier="B",
                message=clarify_message(ranked),
                pending_kind="template",
                pending_slots={
                    "default_tool": "paste_template",
                    "default_arguments": {"template_id": ranked.template_id},
                    "candidates": list(ranked.alternatives),
                },
            )
        elif ranked is not None and not ranked.gold:
            return RouteDecision(
                route="model.clarify",
                tier="B",
                message=(
                    "I don't have a great build for that yet. "
                    "Try: little castle, chicken house, or bridge."
                ),
            )
        from companion.templates import is_gold_template

        if not is_gold_template(str(arguments.get("template_id"))):
            return RouteDecision(
                route="model.clarify",
                tier="B",
                message=(
                    "I don't have a great build for that yet. "
                    "Try: little castle, chicken house, or bridge."
                ),
            )
        cleaned_paste: dict[str, Any] = {
            "template_id": str(arguments.get("template_id"))
        }
        if clear_site:
            cleaned_paste["clear_site"] = True
        forward = arguments.get("forward_blocks")
        if isinstance(forward, int) and not isinstance(forward, bool) and 1 <= forward <= 128:
            cleaned_paste["forward_blocks"] = forward
        else:
            extracted = extract_forward_blocks(prompt)
            if extracted is not None:
                cleaned_paste["forward_blocks"] = extracted
        arguments = cleaned_paste
    elif intent.tool == "place_shape":
        kind = arguments.get("kind")
        if kind not in {"wall", "platform", "box_shell", "solid_box", "cylinder"}:
            return _invalid_model_route()
        cleaned_place: dict[str, Any] = {"kind": kind}
        for key, lo, hi in (
            ("length", 2, 48),
            ("height", 1, 32),
            ("width", 1, 32),
            ("depth", 1, 32),
        ):
            if key in arguments and arguments.get(key) is not None:
                value = arguments.get(key)
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or not lo <= value <= hi
                ):
                    return _invalid_model_route()
                cleaned_place[key] = value
        if "roof" in arguments and arguments.get("roof") is not None:
            if not isinstance(arguments.get("roof"), bool):
                return _invalid_model_route()
            cleaned_place["roof"] = bool(arguments.get("roof"))
        if arguments.get("clear_site") is True or wants_clear_site(prompt):
            cleaned_place["clear_site"] = True
        if "material" in arguments and arguments.get("material") is not None:
            material = arguments.get("material")
            if not isinstance(material, str):
                return _invalid_model_route()
            normalized = _normalize_material(material)
            if normalized is None:
                return _invalid_model_route()
            cleaned_place["material"] = normalized
        arguments = cleaned_place
    elif intent.tool == "finish_wall":
        cleaned: dict[str, Any] = {}
        if "height" in arguments and arguments.get("height") is not None:
            height = arguments.get("height")
            if (
                not isinstance(height, int)
                or isinstance(height, bool)
                or not 0 <= height <= 128
            ):
                return _invalid_model_route()
            if height >= 2:
                cleaned["height"] = height
        if "material" in arguments and arguments.get("material") is not None:
            material = arguments.get("material")
            if not isinstance(material, str):
                return _invalid_model_route()
            normalized = _normalize_material(material)
            if normalized is None:
                return _invalid_model_route()
            cleaned["material"] = normalized
        arguments = cleaned
    elif intent.tool == "finish_floor":
        cleaned_floor: dict[str, Any] = {}
        mode = arguments.get("mode", "fill")
        if mode is None:
            mode = "fill"
        if mode not in {"fill", "replace", "clear"}:
            return _invalid_model_route()
        cleaned_floor["mode"] = mode
        if "material" in arguments and arguments.get("material") is not None:
            material = arguments.get("material")
            if not isinstance(material, str):
                return _invalid_model_route()
            normalized = _normalize_material(material)
            if normalized is None:
                return _invalid_model_route()
            cleaned_floor["material"] = normalized
        if mode != "clear" and "material" not in cleaned_floor:
            # Held-item resolution happens natively; empty material is allowed.
            pass
        arguments = cleaned_floor
    elif intent.tool == "undo_last":
        arguments = {}
    else:
        return _invalid_model_route()
    risk = (
        "bounded"
        if intent.tool
        in {
            "summon_entity",
            "paste_template",
            "finish_wall",
            "finish_floor",
            "place_shape",
        }
        else "safe"
    )
    return RouteDecision(
        route=f"model.{intent.tool}",
        tier="B",
        action=_action(job_id, intent.tool, arguments, risk=risk),
    )


def _invalid_model_route() -> RouteDecision:
    return RouteDecision(
        route="model.invalid",
        tier="B",
        message="I’m not sure about those details. Could you try saying it another way?",
    )

