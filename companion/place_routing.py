"""Deterministic routes for place_shape (sized walls/platforms/boxes/towers)."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from companion.dimensions import (
    Dims,
    extract_material_candidate,
    is_enclosure_ask,
    looks_like_material_token,
    over_budget_box,
    over_budget_platform,
    over_budget_span,
    over_budget_wall,
    parse_dims,
    parse_length_height,
    strip_politeness,
    wall_nxn_ambiguous,
)
from companion.perception import SemanticSceneV1, best_opening

if TYPE_CHECKING:
    from companion.routing import RouteDecision


def _with_clear_site(args: dict[str, Any], prompt: str) -> dict[str, Any]:
    from companion.routing import wants_clear_site

    out = dict(args)
    if wants_clear_site(prompt):
        out["clear_site"] = True
    return out


def finishable_opening_present(scene: SemanticSceneV1 | None) -> bool:
    """True when Level-1 geometry reports a medium/high confidence opening."""
    opening = best_opening(scene)
    if opening is None:
        return False
    return opening.confidence in {"high", "medium"}


def rewrite_wall_place_to_finish(
    job_id: str,
    place_args: dict[str, Any],
    scene: SemanticSceneV1 | None,
) -> RouteDecision | None:
    """When a free-standing wall ask faces a finishable opening, finish instead."""
    from companion.routing import RouteDecision, _action

    if not finishable_opening_present(scene):
        return None
    args: dict[str, Any] = {}
    height = place_args.get("height")
    if isinstance(height, int) and 2 <= height <= 128:
        args["height"] = height
    material = place_args.get("material")
    if isinstance(material, str) and material:
        args["material"] = material
    return RouteDecision(
        route="perception.finish_visible_wall",
        tier="A",
        action=_action(job_id, "finish_wall", args, risk="bounded"),
    )


def _material_arg(text: str) -> str | None:
    """Return normalized material, None if absent, or '__bad__' if unusable.

    Named materials must be resolved here. Omitting material lets the native
    executor fall back to the held item — never do that when the player named
    a block (even an unusable one; return ``__bad__`` / clarify instead).
    """
    from companion.routing import _normalize_material

    raw = extract_material_candidate(text)
    if raw is None or not looks_like_material_token(raw):
        return None
    material = _normalize_material(raw)
    if material is None:
        return "__bad__"
    return material


_PLANT_TEMPLATE_RX = re.compile(
    r"\b(?:garden|farm|greenhouse|orchard|allotment|crop|crops|farmland|"
    r"plants?|flowers?|veggie|vegetable|herb(?:s)?|wheat|carrot|potato|"
    r"pumpkin|melon|berr(?:y|ies)|sugar\s*cane|sugarcane)\b",
    re.I,
)
# Explicit structural shape words — enclosure/platform routes may still win.
_STRUCTURAL_SHAPE_RX = re.compile(
    r"\b(?:platform|pad|deck|raft|wall|walls|box|room|shell|tower|pillar|"
    r"enclosure|fence|fencing|perimeter|surround|courtyard|arena|compound)\b",
    re.I,
)


def is_plant_template_intent(text: str) -> bool:
    """Garden/farm/plant asks should paste templates, not stone platforms."""
    if not _PLANT_TEMPLATE_RX.search(text):
        return False
    # Allow place_shape when the player clearly wants a structural shape.
    return not _STRUCTURAL_SHAPE_RX.search(text)


# Decorative gold bridges stay on templates; generic "make a bridge" spans.
_FANCY_BRIDGE_RX = re.compile(
    r"\b(?:rope(?:y)?|swing(?:ing|y)?|vine|scary\s+rope)\b",
    re.I,
)
_BRIDGE_INTENT_RX = re.compile(
    r"\b(?:bridge)\b",
    re.I,
)
_PATH_INTENT_RX = re.compile(
    r"(?:"
    r"\b(?:clear|make|build|lay|pave|cut)\b.{"
    r"0,24}\b(?:path|trail|footpath|walkway)\b"
    r"|\b(?:path|trail|footpath)\b.{"
    r"0,24}\b(?:to|from|across|through|toward|towards|\d)\b"
    r"|\b(?:a\s+)?(?:footpath|trail|path|walkway)\b"
    r"|\bclear\s+(?:a\s+)?(?:path|trail|footpath)\b"
    r"|\b(?:gravel|dirt|cobble|cobblestone|stone|oak|wood)\s+path\b"
    r")",
    re.I,
)
_ROAD_INTENT_RX = re.compile(
    r"\b(?:road|highway|street)\b"
    r"|\bpave\s+(?:a\s+)?(?:path|road)\b"
    r"|\b(?:make|build|lay)\s+(?:a\s+)?(?:road|path)\b",
    re.I,
)
# Stairs / steps connecting ground to a door or entrance.
_STAIRS_TO_DOOR_RX = re.compile(
    r"\b(?:stairs?|steps|staircase|stairway)\b.{"
    r"0,48}\b(?:door|doorway|entrance|entry)\b"
    r"|\b(?:door|doorway|entrance|entry)\b.{"
    r"0,48}\b(?:stairs?|steps|staircase|stairway)\b"
    r"|\b(?:stairs?|steps)\s+up\s+to\b.{"
    r"0,24}\b(?:door|doorway|entrance|entry|it|that)\b",
    re.I,
)


def is_fancy_bridge_template(text: str) -> bool:
    """True for curated decorative bridges (rope/swing); pier/dock stay templates."""
    # Explicit short-oak ask keeps the tiny gold schem (wide gaps use parametric).
    if re.search(r"\bshort\s+oak\s+bridge\b", text, re.I):
        return True
    if _BRIDGE_INTENT_RX.search(text) and _FANCY_BRIDGE_RX.search(text):
        return True
    # Bare pier/dock (no bridge/road word) → gold dock/pier paste, not a span.
    return bool(
        re.search(r"\b(?:pier|dock|wharf|boardwalk)\b", text, re.I)
        and not re.search(r"\b(?:bridge|road|path|highway|street)\b", text, re.I)
    )


def _span_width(text: str, dims: Dims, length_ex: int | None, default: int) -> int:
    """Width for bridge/road: '3 wide', bare NxM → width, else default 3–5."""
    wide = re.search(r"\b(\d+)\s*(?:blocks?\s+)?wide\b", text, re.I)
    if wide:
        return max(1, min(8, int(wide.group(1))))
    if dims.a is not None and dims.b is not None and dims.c is None:
        # "bridge 20x4" → length×width when length phrase absent
        if length_ex is None:
            return max(1, min(8, dims.b))
    if re.search(r"\b(?:wide|broad)\b", text, re.I):
        return 5
    return default


def _span_length(text: str, dims: Dims, length_ex: int | None) -> int | None:
    """Optional explicit length; None means native raycast across the gap."""
    if length_ex is not None:
        return length_ex
    if dims.a is not None and dims.b is not None and dims.c is None:
        return dims.a
    if dims.a is not None and dims.b is None:
        # Lone number with bridge/road often means length ("bridge 40")
        if re.search(r"\b\d+\b", text):
            return dims.a
    m = re.search(
        r"\b(\d+)\s*(?:blocks?\s+)?(?:long|across|forward)\b",
        text,
        re.I,
    )
    if m:
        return int(m.group(1))
    return None


_ROUTE_KIND = r"(?:path|trail|footpath|walkway|bridge|road)"

# Explicit "marking" verbs, or bare "start/begin a path|bridge" (marker flow).
_START_MARK_RX = re.compile(
    rf"\b(?:start|begin|lets?|let'?s)\b.{{0,28}}\b(?:mark(?:ing)?|markers?)\b.{{0,28}}\b{_ROUTE_KIND}\b"
    rf"|\b(?:start|begin|lets?|let'?s)\b.{{0,20}}\b{_ROUTE_KIND}\b.{{0,20}}\b(?:mark(?:ing)?|markers?)\b"
    rf"|\bmark(?:ing)?\s+(?:a\s+|the\s+)?{_ROUTE_KIND}\b"
    rf"|\b(?:start|begin|lets?|let'?s)\s+(?:marking\s+)?(?:a\s+|the\s+)?{_ROUTE_KIND}\b"
    rf"|\b(?:make|build|lay)\s+(?:a\s+|the\s+)?{_ROUTE_KIND}\b.{{0,24}}\b(?:markers?|gold)\b"
    rf"|\b(?:markers?|gold\s+blocks?)\b.{{0,24}}\b{_ROUTE_KIND}\b",
    re.I,
)
_FINISH_MARK_RX = re.compile(
    rf"\b(?:finish|finished|complete|completed|done)\b.{{0,36}}\b(?:the\s+|this\s+|my\s+|our\s+)?"
    rf"(?:{_ROUTE_KIND}|mark(?:ing)?|markers?)\b"
    rf"|\b(?:finish|finished|complete|completed|done)\s+marking\b"
    rf"|\b(?:{_ROUTE_KIND})\s+(?:is\s+)?(?:done|finished|complete|ready)\b"
    rf"|\b(?:that'?s\s+it|all\s+done|ready)\b.{{0,20}}\b(?:{_ROUTE_KIND}|markers?|marking)\b"
    rf"|\bconnect\s+(?:the\s+|my\s+)?(?:markers?|dots|gold|path|bridge|trail)\b"
    rf"|\b(?:link|join)\s+(?:the\s+)?(?:markers?|gold)\b",
    re.I,
)
_CANCEL_MARK_RX = re.compile(
    rf"\b(?:cancel|stop|abort)\b.{{0,24}}\b(?:mark(?:ing)?|markers?|{_ROUTE_KIND})\b"
    rf"|\bnever\s*mind\s+(?:the\s+|this\s+)?(?:{_ROUTE_KIND}|markers?|marking)\b",
    re.I,
)


def _mark_kind(text: str) -> str:
    if re.search(r"\bbridge\b", text, re.I):
        return "bridge"
    return "path"


def route_place_shape(
    prompt: str,
    job_id: str,
    *,
    has_place_shape: bool = True,
    has_finishable_wall: bool = False,
    has_mark_route: bool = True,
) -> RouteDecision | None:
    from companion.routing import RouteDecision, _action

    text = strip_politeness(prompt)
    # Capability gap (no dig tool) — not a morality refuse. Keep TNT out of
    # this pattern so "give me 5 tnt" routes to give_item.
    if re.search(
        r"\b(?:dig|quarry|mine\s+out|blow\s+up|explode)\b",
        text,
        re.I,
    ) and re.search(r"\b(?:hole|pit|tunnel|quarry|\d)\b", text, re.I):
        return RouteDecision(
            route="policy.refuse_dig",
            tier="S",
            message="I can't dig big holes. Try a platform or wall instead.",
        )

    # Do not let platform/box/wall patterns steal garden/farm plant intents.
    # Enclosure routes still win when structural words are present
    # ("fence around my garden", "20x20 rock enclosure").
    if is_plant_template_intent(text):
        return None

    # Flow A: start / finish / cancel ordered gold-block markers.
    if _CANCEL_MARK_RX.search(text):
        if not has_mark_route:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't mark paths yet — try again in a moment.",
            )
        return RouteDecision(
            route="pattern.mark_route_cancel",
            tier="S",
            action=_action(job_id, "mark_route", {"action": "cancel"}, risk="bounded"),
        )
    if _START_MARK_RX.search(text):
        # "start a path 40 long" stays a gaze/length place_shape — not markers.
        dims_early = parse_dims(text)
        length_early, _ = parse_length_height(text)
        sized_start = length_early is not None or (
            dims_early.a is not None
            and re.search(r"\b(?:long|across|x|\d+\s*x\s*\d+)\b", text, re.I)
        )
        if not sized_start:
            if not has_mark_route:
                return RouteDecision(
                    route="grammar.clarify_place_unavailable",
                    tier="S",
                    message="I can't mark paths yet — try again in a moment.",
                )
            kind = _mark_kind(text)
            return RouteDecision(
                route="pattern.mark_route_start",
                tier="S",
                action=_action(
                    job_id,
                    "mark_route",
                    {"action": "start", "kind": kind},
                    risk="bounded",
                ),
            )
    # "finish the path/bridge" — connect markers (session or nearby scan).
    if _FINISH_MARK_RX.search(text):
        if not has_mark_route:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't mark paths yet — try again in a moment.",
            )
        kind = _mark_kind(text)
        dims = parse_dims(text)
        length_ex, _ = parse_length_height(text)
        width = _span_width(text, dims, length_ex, default=3)
        args: dict[str, Any] = {"action": "finish", "kind": kind, "width": width}
        mat = _material_arg(text)
        if mat and mat != "__bad__":
            args["material"] = mat
        elif kind == "bridge":
            args["material"] = "oak_planks"
        else:
            args["material"] = "dirt_path"
        return RouteDecision(
            route="pattern.mark_route_finish",
            tier="A",
            action=_action(
                job_id, "mark_route", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Stairs / steps from ground up to a door (gaze or nearby).
    if _STAIRS_TO_DOOR_RX.search(text):
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        dims_st = parse_dims(text)
        length_st, _ = parse_length_height(text)
        width = _span_width(text, dims_st, length_st, default=2)
        args_st: dict[str, Any] = {"kind": "stairs_to", "width": width}
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Try: oak stairs to the door",
            )
        if mat:
            # "oak stairs…" often normalizes to oak_planks — prefer stair blocks.
            if mat.endswith("_planks") and re.search(r"\bstairs?\b", text, re.I):
                args_st["material"] = mat[: -len("_planks")] + "_stairs"
            else:
                args_st["material"] = mat
        else:
            args_st["material"] = "oak_stairs"
        return RouteDecision(
            route="pattern.place_stairs_to",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args_st, text), risk="bounded"
            ),
        )

    dims = parse_dims(text)
    length_ex, height_ex = parse_length_height(text)
    has_size = any(
        v is not None for v in (dims.a, dims.b, dims.c, length_ex, height_ex)
    )

    # Bridge / road / path — parametric span (not short schem paste).
    # Fancy named bridges (rope…) still paste; pier/dock stay templates.
    # Native prefers markers when present, else gaze-forward.
    bridge_ask = bool(_BRIDGE_INTENT_RX.search(text)) and not is_fancy_bridge_template(
        text
    )
    path_ask = bool(_PATH_INTENT_RX.search(text)) and not bridge_ask
    road_ask = bool(_ROAD_INTENT_RX.search(text)) and not bridge_ask and not path_ask
    # Bare "path" / "a path" without trail verbs still counts as path.
    if not path_ask and not road_ask and not bridge_ask:
        if re.fullmatch(
            r"(?:please\s+)?(?:a\s+)?(?:path|trail|footpath|walkway)[.!]?",
            text,
            re.I,
        ):
            path_ask = True
    if bridge_ask or road_ask or path_ask:
        if bridge_ask:
            kind = "bridge"
            default_mat = "oak_planks"
            default_len = 24
            route_name = "pattern.place_bridge"
        elif path_ask:
            kind = "path"
            default_mat = "dirt_path"
            default_len = 48
            route_name = "pattern.place_path"
        else:
            kind = "road"
            default_mat = "cobblestone"
            default_len = 48
            route_name = "pattern.place_road"
        width = _span_width(text, dims, length_ex, default=3)
        length = _span_length(text, dims, length_ex)
        if length is not None and length > 1024:
            return RouteDecision(
                route="grammar.clarify_span_length",
                tier="S",
                message="That's too far for one go. Try up to 1024 blocks — like: path 200 long",
            )
        if length is not None and over_budget_span(length, width):
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That's too long for me. Try a bridge, road, or path up to 1024 blocks.",
            )
        if over_budget_span(length or default_len, width):
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That's too wide for me. Try a width up to 8.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args: dict[str, Any] = {"kind": kind, "width": width}
        if length is not None:
            args["length"] = length
        mat = _material_arg(text)
        if mat == "__bad__":
            hint = {
                "bridge": "oak bridge",
                "path": "dirt path",
                "road": "cobble road",
            }[kind]
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message=f"What block should I use? Try: {hint}",
            )
        if mat:
            args["material"] = mat
        else:
            args["material"] = default_mat
        return RouteDecision(
            route=route_name,
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Platform / pad
    if re.search(r"\b(?:platform|pad|deck|raft)\b", text, re.I) and (
        has_size or re.search(r"\b(?:build|make|place|put)\b", text, re.I)
    ):
        w = dims.a or length_ex or 5
        d = dims.b or dims.a or height_ex or w
        if over_budget_platform(w, d):
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That's too big for me. Try a platform up to 32×32.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args: dict[str, Any] = {"kind": "platform", "width": w, "depth": d}
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Try: 5x5 oak platform",
            )
        if mat:
            args["material"] = mat
        return RouteDecision(
            route="pattern.place_platform",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Tower with height digits (beats watchtower paste)
    tower = re.search(
        r"\b(?:tower|pillar)\b",
        text,
        re.I,
    ) and (height_ex is not None or (dims.a and not dims.b))
    if tower and not re.search(r"\bwatchtower\b", text, re.I):
        height = height_ex or dims.a or 10
        width = 3
        if dims.a and dims.b:
            width = min(dims.a, 7)
            height = height_ex or dims.b
        if height > 32 or height < 2:
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="Pick a tower height between 2 and 32.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args = {
            "kind": "box_shell",
            "width": width,
            "depth": width,
            "height": height,
            "roof": True,
        }
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Try: tower 10 tall with stone",
            )
        if mat:
            args["material"] = mat
        return RouteDecision(
            route="pattern.place_tower",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Enclosure / perimeter walls (prefer hollow box_shell, no roof).
    # Footprint NxN or N×M; wall height defaults to 4 (2 for fence) unless said.
    if is_enclosure_ask(text, dims) and (
        has_size
        or re.search(
            r"\b(?:build|make|place|put|wall|box|fence|surround)\b",
            text,
            re.I,
        )
    ):
        if dims.a is not None and dims.b is not None and dims.c is None:
            w, d = dims.a, dims.b
        elif dims.a is not None and dims.b is None:
            w = d = dims.a
        elif length_ex is not None:
            w = d = length_ex
        else:
            w = d = 8
        fence_ask = bool(
            re.search(r"\b(?:fence|fencing|fences)\b", text, re.I)
            and not re.search(
                r"\b(?:rock|rocks|rocky|stone|cobble|cobblestone|brick|bricks|"
                r"quartz|glass|dirt|oak|wood|wooden)\b",
                text,
                re.I,
            )
        )
        default_h = 2 if fence_ask else 4
        h = height_ex or default_h
        # 3-number dims on enclosure phrases are rare; treat as w×d×h.
        if dims.c is not None:
            w, d, h = dims.a or w, dims.b or d, dims.c
        if over_budget_box(w, d, h, roof=False):
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That enclosure is too big. Try up to 32×32 and 24 high.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args: dict[str, Any] = {
            "kind": "box_shell",
            "width": w,
            "depth": d,
            "height": h,
            "roof": False,
        }
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Try: 20x20 rock enclosure",
            )
        if mat:
            args["material"] = mat
        elif fence_ask:
            args["material"] = "oak_fence"
        return RouteDecision(
            route="pattern.place_enclosure",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Box / room / hollow shell (roofed unless "open" / "no roof")
    if re.search(r"\b(?:box|room|shell|hollow\s+cube|cube)\b", text, re.I) and has_size:
        if dims.c is not None:
            w, d, h = dims.a or 5, dims.b or 5, dims.c
        elif dims.a and dims.b:
            w, d, h = dims.a, dims.b, 4
        else:
            w = d = dims.a or 5
            h = height_ex or 4
        solid = bool(re.search(r"\bsolid\b", text, re.I))
        kind = "solid_box" if solid else "box_shell"
        roof = not bool(
            re.search(r"\b(?:open(?:-|\s*)top|no\s+roof|without\s+a?\s*roof)\b", text, re.I)
        )
        if over_budget_box(w, d, h, roof=roof) and kind == "box_shell":
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That box is too big. Try something closer to 12×12×8.",
            )
        if kind == "solid_box" and w * d * h > 4096:
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That solid box is too big. Try a smaller size.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args = {"kind": kind, "width": w, "depth": d, "height": h, "roof": roof}
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Try: 7x7x5 stone box",
            )
        if mat:
            args["material"] = mat
        return RouteDecision(
            route="pattern.place_box",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Cylinder (Wave 3 primitive)
    radius_m = re.search(r"\bradius\s+(\d+)\b", text, re.I)
    if re.search(r"\b(?:cylinder|cyl)\b", text, re.I) and (
        has_size or radius_m or height_ex is not None
    ):
        radius = int(radius_m.group(1)) if radius_m else (dims.a or length_ex or 3)
        height = height_ex or dims.b or 8
        if radius > 16 or height > 32 or (3.14 * radius * radius * height) > 4096:
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That cylinder is too big. Try a smaller radius or height.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args = {"kind": "cylinder", "width": radius * 2, "depth": radius * 2, "height": height}
        # store radius in width/2 convention; native reads width as diameter
        mat = _material_arg(text)
        if mat and mat != "__bad__":
            args["material"] = mat
        return RouteDecision(
            route="pattern.place_cylinder",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    # Walls with size — not finish phrasing
    if re.search(r"\bwalls?\b", text, re.I) and not re.search(
        r"\b(?:finish|finsh|complete|fill\s+in|between|remaining|open)\b",
        text,
        re.I,
    ):
        # The native executor repeats this check against its fresh geometry
        # inspection before any mutation.  Routing can receive the same
        # semantic fact in offline/live preflight so a visible opening is
        # never represented as a free-standing wall.
        if has_finishable_wall:
            args: dict[str, Any] = {}
            if height_ex is not None:
                if not 2 <= height_ex <= 128:
                    return RouteDecision(
                        route="grammar.clarify_wall_height",
                        tier="S",
                        message="How tall should it be? Try: finish this wall 12 blocks high",
                    )
                args["height"] = height_ex
            mat = _material_arg(text)
            if mat == "__bad__":
                return RouteDecision(
                    route="grammar.clarify_wall_material",
                    tier="S",
                    message="What block should I use? Try: finish this wall with quartz",
                )
            if mat:
                args["material"] = mat
            return RouteDecision(
                route="perception.finish_visible_wall",
                tier="A",
                action=_action(job_id, "finish_wall", args, risk="bounded"),
            )
        if wall_nxn_ambiguous(text, dims):
            return RouteDecision(
                route="grammar.clarify_wall_shape",
                tier="S",
                message="A long wall or a square wall? Try: wall 20 long 5 high",
                pending_kind="wall_shape",
                pending_slots={"dims": [dims.a, dims.b]},
            )
        length = length_ex
        height = height_ex
        if dims.a is not None and dims.b is not None and dims.c is None:
            # Bare/disambiguated NxN → length × height (never silently drop width).
            # "20x20 high", "15x10 tall", "wall 12 by 6 wide" all mean a×b.
            if length is None or height is None:
                length = dims.a if length is None else length
                height = dims.b if height is None else height
        length = length or 8
        height = height or 4
        if not has_size and not re.search(
            r"\b(?:build|make|place|put)\b.*\bwalls?\b", text, re.I
        ):
            return None
        if not has_size:
            # "build a stone wall" without size → finish_wall path elsewhere
            return None
        if over_budget_wall(length, height):
            return RouteDecision(
                route="grammar.refuse_place_budget",
                tier="S",
                message="That wall is too big. Try up to 48 long and 32 high.",
            )
        if not has_place_shape:
            return RouteDecision(
                route="grammar.clarify_place_unavailable",
                tier="S",
                message="I can't place shapes yet — try again in a moment.",
            )
        args = {"kind": "wall", "length": length, "height": height}
        mat = _material_arg(text)
        if mat == "__bad__":
            return RouteDecision(
                route="grammar.clarify_place_material",
                tier="S",
                message="What block should I use? Hold one or say: stone wall 10 high",
            )
        if mat:
            args["material"] = mat
        return RouteDecision(
            route="pattern.place_wall",
            tier="A",
            action=_action(
                job_id, "place_shape", _with_clear_site(args, text), risk="bounded"
            ),
        )

    return None
