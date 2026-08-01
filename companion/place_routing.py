"""Deterministic routes for place_shape (sized walls/platforms/boxes/towers)."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from companion.dimensions import (
    extract_material_candidate,
    looks_like_material_token,
    over_budget_box,
    over_budget_platform,
    over_budget_wall,
    parse_dims,
    parse_length_height,
    strip_politeness,
    wall_nxn_ambiguous,
)
from companion.perception import SemanticSceneV1, best_opening

if TYPE_CHECKING:
    from companion.routing import RouteDecision


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
    """Return normalized material, None if absent, or '__bad__' if unusable."""
    from companion.routing import _normalize_material

    raw = extract_material_candidate(text)
    if raw is None or not looks_like_material_token(raw):
        return None
    material = _normalize_material(raw)
    if material is None:
        return "__bad__"
    return material


def route_place_shape(
    prompt: str,
    job_id: str,
    *,
    has_place_shape: bool = True,
    has_finishable_wall: bool = False,
) -> RouteDecision | None:
    from companion.routing import RouteDecision, _action

    text = strip_politeness(prompt)
    if re.search(
        r"\b(?:dig|quarry|mine\s+out|blow\s+up|tnt|explode)\b",
        text,
        re.I,
    ) and re.search(r"\b(?:hole|pit|tunnel|quarry|\d)\b", text, re.I):
        return RouteDecision(
            route="policy.refuse_dig",
            tier="S",
            message="I can't dig big holes. Try a platform or wall instead.",
        )

    dims = parse_dims(text)
    length_ex, height_ex = parse_length_height(text)
    has_size = any(
        v is not None for v in (dims.a, dims.b, dims.c, length_ex, height_ex)
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
            action=_action(job_id, "place_shape", args, risk="bounded"),
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
            action=_action(job_id, "place_shape", args, risk="bounded"),
        )

    # Box / room / hollow shell
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
        if over_budget_box(w, d, h) and kind == "box_shell":
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
        args = {"kind": kind, "width": w, "depth": d, "height": h, "roof": True}
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
            action=_action(job_id, "place_shape", args, risk="bounded"),
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
            action=_action(job_id, "place_shape", args, risk="bounded"),
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
            # Explicit long/high already checked; treat as length x height
            if re.search(r"\b(?:long|curtain)\b", text, re.I):
                length = dims.a
                height = dims.b
            elif re.search(r"\b(?:high|tall)\b", text, re.I) and length_ex is None:
                length = length or 8
                height = dims.a if height is None else height
            else:
                length = dims.a
                height = dims.b
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
            action=_action(job_id, "place_shape", args, risk="bounded"),
        )

    return None
