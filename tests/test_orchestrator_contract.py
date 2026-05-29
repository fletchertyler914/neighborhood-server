"""Contract tests for orchestrator job payload (no server)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.job import JobRequest, build_user_message
from agent.orchestrator import (
    _normalize_tool_args_for_prompt,
    _normalize_tool_call_for_prompt,
)


def test_job_request_bedrock_name():
    req = JobRequest(
        player=".LunarLicense582",
        uuid="00000000-0000-0000-0009-01f42260e0d1",
        prompt="build platform here",
        x=100.5,
        y=80.0,
        z=-50.2,
    )
    msg = build_user_message(req)
    assert ".LunarLicense582" in msg
    assert "build platform" in msg


def _req(prompt: str, player: str = "firecrab93") -> JobRequest:
    return JobRequest(player=player, uuid="u", prompt=prompt, x=0, y=80, z=0)


def test_front_drill_prompt_forces_positive_forward_offset():
    args = {"player": "firecrab93", "depth": 50, "forward_offset": -1}
    _normalize_tool_args_for_prompt(
        _req("drill a 50 block hole in frnot of me"),
        "mine_shaft_at_player",
        args,
    )
    assert args["forward_offset"] == 1


def test_bridge_prompt_rewrites_mine_shaft_to_bridge():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a bridge across the water in front of me 2 blocks wide"),
        "mine_shaft_at_player",
        {"player": "firecrab93", "depth": 24, "forward_offset": 2},
    )
    assert name == "build_bridge_at_player"
    assert args["player"] == "firecrab93"
    assert args["length"] == 24
    assert args["width"] == 2


def test_bridge_prompt_pulls_explicit_width_from_prompt():
    name, args = _normalize_tool_call_for_prompt(
        _req("plank a 3 wide path across the water 20 blocks long"),
        "fill_box",
        {"x1": 0, "y1": 79, "z1": 0, "x2": 19, "y2": 79, "z2": 2, "block": "oak_planks"},
    )
    assert name == "build_bridge_at_player"
    assert args["width"] == 3
    assert args["length"] == 20


def test_house_in_front_of_me_rewrites_to_at_player():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a sand fort in front of me with a door"),
        "build_house",
        {"center_x": 9000, "y": 60, "center_z": 9000, "width": 7},
    )
    assert name == "build_house_at_player"
    assert args["player"] == "firecrab93"
    assert args["width"] == 7
    assert args["wall_block"] == "sandstone"
    assert args["roof_block"] == "sandstone_slab"
    assert "center_x" not in args


def test_house_inferred_when_model_picks_build_sphere():
    name, args = _normalize_tool_call_for_prompt(
        _req("build me a wooden cabin in front of me with a door and 2 windows"),
        "build_sphere",
        {"center_x": 0, "center_y": 80, "center_z": 0, "radius": 5, "block": "oak_planks"},
    )
    assert name == "paste_template_at_player"
    assert args["template_id"] == "house_cottage_small"


def test_drill_prompt_keeps_mine_shaft_tool():
    name, args = _normalize_tool_call_for_prompt(
        _req("drill 50 down in front of me"),
        "mine_shaft_at_player",
        {"player": "firecrab93", "depth": 50, "forward_offset": -1},
    )
    assert name == "mine_shaft_at_player"
    assert args["forward_offset"] == 1


def test_non_bridge_house_prompt_left_alone():
    name, args = _normalize_tool_call_for_prompt(
        _req("build me a glass sphere of radius 10"),
        "build_sphere",
        {"center_x": 0, "center_y": 80, "center_z": 0, "radius": 10, "block": "glass"},
    )
    assert name == "build_sphere"
    assert args["radius"] == 10


# --- castle routing -----------------------------------------------------


def test_castle_prompt_rewrites_solid_cylinder_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a castle"),
        "build_cylinder",
        {"center_x": 9180, "y": 69, "center_z": 9178, "radius": 10, "height": 20, "block": "stone_bricks"},
    )
    assert name == "paste_template_at_player"
    assert args["player"] == "firecrab93"
    assert args["template_id"] == "castle_small_keep"
    assert "center_x" not in args


def test_castle_prompt_rewrites_fill_box_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a stone fortress"),
        "fill_box",
        {"x1": 0, "y1": 60, "z1": 0, "x2": 14, "y2": 70, "z2": 14, "block": "stone"},
    )
    assert name == "paste_template_at_player"
    assert args["player"] == "firecrab93"
    assert args["template_id"] == "castle_small_keep"


def test_castle_with_explicit_size_stays_parametric():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a castle exactly 21 blocks wide"),
        "build_cylinder",
        {"center_x": 0, "y": 80, "center_z": 0, "radius": 10, "height": 20, "block": "stone"},
    )
    assert name == "build_castle_at_player"
    assert args["player"] == "firecrab93"


def test_castle_left_alone_when_user_asks_for_cylinder():
    name, _ = _normalize_tool_call_for_prompt(
        _req("build a stone cylinder radius 5"),
        "build_cylinder",
        {"center_x": 0, "y": 80, "center_z": 0, "radius": 5, "height": 10, "block": "stone"},
    )
    assert name == "build_cylinder"


# --- give_item routing --------------------------------------------------


def test_give_diamond_pickaxe_rewrites_give_haste_to_give_item():
    name, args = _normalize_tool_call_for_prompt(
        _req("give me a diamond pickaxe"),
        "give_haste",
        {"player": "firecrab93", "duration_sec": 60, "amplifier": 1},
    )
    assert name == "give_item"
    assert args == {"player": "firecrab93", "item": "diamond_pickaxe"}


def test_give_item_rewrites_fawe_give():
    name, args = _normalize_tool_call_for_prompt(
        _req("gimme a diamond sword"),
        "fawe_as_player",
        {"player": "firecrab93", "command": "//give @p diamond_sword"},
    )
    assert name == "give_item"
    assert args == {"player": "firecrab93", "item": "diamond_sword"}


def test_give_stack_of_stone_count_64():
    name, args = _normalize_tool_call_for_prompt(
        _req("gimme a stack of stone"),
        "give_haste",
        {"player": "firecrab93"},
    )
    assert name == "give_item"
    # falls back to a non-aliased item id from the prompt
    assert args["count"] == 64


def test_give_haste_for_haste_prompt_left_alone():
    name, args = _normalize_tool_call_for_prompt(
        _req("give me haste 2 for 30 minutes"),
        "give_haste",
        {"player": "firecrab93", "duration_sec": 1800, "amplifier": 2},
    )
    assert name == "give_haste"
    assert args["amplifier"] == 2


def test_chicken_coop_rewrites_build_house_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("make me a chicken coop with 4 chickens"),
        "build_house",
        {
            "center_x": 9156,
            "y": 69,
            "center_z": 9147,
            "wall_block": "pumpkin",
            "roof_block": "spruce_roof_tile",
        },
    )
    assert name == "paste_template_at_player"
    assert args["player"] == "firecrab93"
    assert args["template_id"] == "chicken_coop_small"


def test_pig_pen_rewrites_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a pig pen"),
        "fill_box",
        {"x1": 0, "y1": 64, "z1": 0, "x2": 10, "y2": 66, "z2": 10, "block": "oak_fence"},
    )
    assert name == "paste_template_at_player"
    assert args["player"] == "firecrab93"
    assert args["template_id"] == "pig_pen_small"


def test_horse_stable_rewrites_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("build a horse stable with 2 horses"),
        "build_house_at_player",
        {"player": "firecrab93"},
    )
    assert name == "paste_template_at_player"
    assert args["template_id"] == "horse_stable_small"


def test_rabbit_hutch_rewrites_to_template():
    name, args = _normalize_tool_call_for_prompt(
        _req("build me a rabbit hutch"),
        "build_house_at_player",
        {"player": "firecrab93"},
    )
    assert name == "paste_template_at_player"
    assert args["template_id"] == "rabbit_hutch_small"


def test_pen_keeps_block_overrides_from_model():
    name, args = _normalize_tool_call_for_prompt(
        _req("make a sheep pen with spruce fence"),
        "build_platform",
        {"center_x": 0, "y": 64, "center_z": 0, "block": "spruce_fence"},
    )
    assert name == "build_animal_pen_at_player"
    assert args["animal"] == "sheep"


def test_spawn_n_chickens_from_give_item_routes_to_summon_entity():
    req = JobRequest(
        player="firecrab93",
        uuid="u",
        prompt="spawn me 4 chickens",
        x=100,
        y=64,
        z=200,
    )
    name, args = _normalize_tool_call_for_prompt(
        req,
        "give_item",
        {"player": "firecrab93", "item": "chicken", "count": 4},
    )
    assert name == "summon_entity"
    assert args["entity"] == "chicken"
    assert args["x"] == 100 and args["y"] == 64 and args["z"] == 200
    assert args["count"] == 4


def test_bind_request_player_rejects_uuid_hallucination():
    from agent.orchestrator.app import _bind_request_player

    req = JobRequest(
        player="firecrab93",
        uuid="u",
        prompt="hollow sphere",
        x=0,
        y=64,
        z=0,
    )
    args = {
        "command": "//hsphere stone 5",
        "player": "c07e6ca8-b33b-4ab2-babb-b0d5e6b9367d",
    }
    _bind_request_player("fawe_as_player", args, req)
    assert args["player"] == "firecrab93"
