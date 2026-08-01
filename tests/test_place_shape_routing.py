"""Routing tests for place_shape + gold paste + dig refuse."""

from __future__ import annotations

import yaml
from pathlib import Path

from companion.dimensions import parse_dims
from companion.place_routing import route_place_shape
from companion.routing import route
from companion.session import PlayerSession, resolve_revise
from companion.templates import match_template, reload_catalog


def test_wall_20x20_clarifies() -> None:
    decision = route("build a wall 20x20", "job-1")
    assert decision.action is None
    assert "long wall" in (decision.message or "").lower() or "square" in (
        decision.message or ""
    ).lower()


def test_wall_long_high_places() -> None:
    decision = route("build a wall 20 long 5 high", "job-2")
    assert decision.action is not None
    assert decision.action.tool == "place_shape"
    assert decision.action.arguments["kind"] == "wall"
    assert decision.action.arguments["length"] == 20
    assert decision.action.arguments["height"] == 5


def test_platform_5x5() -> None:
    decision = route("build a 5x5 platform", "job-3")
    assert decision.action is not None
    assert decision.action.tool == "place_shape"
    assert decision.action.arguments["kind"] == "platform"


def test_place_shape_materials_from_live_prompts() -> None:
    """Live shapes suite prompts must resolve real block ids, not shape nouns."""
    cases = [
        ("build a 5x5 oak platform", "platform", "oak_planks"),
        ("build a 5x5 oak planks platform", "platform", "oak_planks"),
        ("5x5 platform with oak planks", "platform", "oak_planks"),
        ("build a cobblestone wall 8 long 4 high", "wall", "cobblestone"),
        ("make a stone wall 10 long 5 high", "wall", "stone"),
        ("build a solid stone box 4x4x3", "solid_box", "stone"),
        ("build a glass box 5x5x4", "box_shell", "glass"),
        ("build a quartz cylinder radius 3 height 4", "cylinder", "quartz_block"),
    ]
    for prompt, kind, material in cases:
        decision = route(prompt, f"mat-{kind}")
        assert decision.action is not None, prompt
        assert decision.action.tool == "place_shape", prompt
        assert decision.action.arguments.get("kind") == kind, prompt
        assert decision.action.arguments.get("material") == material, (
            prompt,
            decision.action.arguments,
        )


def test_extract_material_strips_shape_nouns() -> None:
    from companion.dimensions import extract_material_candidate
    from companion.routing import _normalize_material

    assert extract_material_candidate("build a 5x5 oak platform") == "oak"
    assert extract_material_candidate("build a cobblestone wall 8 long") == "cobblestone"
    assert extract_material_candidate("solid stone box 4x4x3") == "stone"
    assert extract_material_candidate("quartz cylinder radius 3") == "quartz"
    assert _normalize_material("oak platform") == "oak_planks"
    assert _normalize_material("cobblestone_wall") == "cobblestone"
    assert _normalize_material("stone box") == "stone"
    assert _normalize_material("quartz cylinder radius") == "quartz_block"
    assert _normalize_material("oak_planks") == "oak_planks"
    assert _normalize_material("grass_block") == "grass_block"


def test_tower_10_tall_not_watchtower_paste() -> None:
    decision = route("build a tower 10 tall", "job-4")
    assert decision.action is not None
    assert decision.action.tool == "place_shape"
    assert decision.action.arguments["kind"] == "box_shell"


def test_watchtower_pastes_gold() -> None:
    reload_catalog()
    decision = route("build a watchtower", "job-5")
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "watchtower_tall"


def test_little_castle_gold() -> None:
    reload_catalog()
    match = match_template("build a little castle")
    assert match is not None
    assert match.gold
    assert match.template_id == "castle_small_keep"


def test_dig_refused() -> None:
    decision = route("dig a 5x5 hole", "job-6")
    assert decision.action is None
    assert "dig" in (decision.message or "").lower() or "hole" in (
        decision.message or ""
    ).lower()


def test_place_shape_capability_flag() -> None:
    decision = route_place_shape(
        "build a 5x5 platform", "job-7", has_place_shape=False
    )
    assert decision is not None
    assert decision.action is None


def test_yo_daytime_still_works() -> None:
    decision = route("yo make it daytime", "job-8")
    assert decision.action is not None
    assert decision.action.tool == "set_time"


def test_cubed_dims_parse() -> None:
    assert parse_dims("hollow box 12 cubed") == parse_dims("12x12x12")
    assert parse_dims("solid stone cube 8").a == 8
    assert parse_dims("solid stone cube 8").c == 8


def test_lighthouse_not_house_substring() -> None:
    reload_catalog()
    match = match_template("build a lighthouse")
    assert match is not None
    assert match.template_id == "lighthouse_short"
    assert match.gold


def test_wizard_tower_clarifies_not_watchtower() -> None:
    reload_catalog()
    decision = route("build a wizard tower", "job-wiz")
    assert decision.action is None
    assert "clarify" in decision.route


def test_eighty_seed_smoke() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "eighty_seed.yaml"
    doc = yaml.safe_load(path.read_text())
    cases = doc["cases"]
    assert len(cases) >= 80, f"eighty_seed too small: {len(cases)}"
    failures: list[str] = []
    for case in cases:
        expect = case["expect"]
        if expect.get("unresolved_or_clarify"):
            continue
        if case.get("prior"):
            session = PlayerSession()
            session.remember_action(
                tool=case["prior"]["tool"],
                arguments=dict(case["prior"].get("arguments") or {}),
                message="prior",
            )
            decision = resolve_revise(
                prompt=case["prompt"],
                session=session,
                job_id=f"seed-{case['id']}",
            )
            if decision is None:
                failures.append(f"{case['id']}: revise returned None")
                continue
        else:
                decision = route(
                    case["prompt"],
                    f"seed-{case['id']}",
                    has_finishable_wall=bool(
                        (case.get("perception") or {}).get("finishable_opening")
                    ),
                )
        if expect.get("refuse") or expect.get("clarify") or expect.get("cancel"):
            if decision.action is not None and expect.get("clarify"):
                failures.append(f"{case['id']}: wanted clarify got {decision.action}")
            elif expect.get("clarify") and "clarify" not in decision.route:
                failures.append(f"{case['id']}: wanted clarify got {decision.route}")
            continue
        tool = expect.get("tool")
        if tool and (decision.action is None or decision.action.tool != tool):
            failures.append(
                f"{case['id']}: wanted {tool} got "
                f"{None if decision.action is None else decision.action.tool} "
                f"({decision.route})"
            )
            continue
        if tool == "place_shape" and "kind" in expect:
            if decision.action.arguments.get("kind") != expect["kind"]:
                failures.append(f"{case['id']}: kind mismatch")
        if tool == "paste_template" and "template_id" in expect:
            if decision.action.arguments.get("template_id") != expect["template_id"]:
                failures.append(f"{case['id']}: template mismatch")
    assert not failures, "\n".join(failures)
