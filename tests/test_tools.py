"""Tests for agent tools (dry-run, no Docker required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from unittest.mock import patch

from agent.tools import (
    Vec3,
    _normalize_entity_id,
    _normalize_item_id,
    _volume,
    build_animal_pen_at_player,
    build_bridge_at_player,
    build_castle_at_player,
    build_house,
    build_house_at_player,
    build_wall_at_player,
    execute_tool,
    fawe_cyl_at_player,
    fawe_sphere_at_player,
    give_haste,
    give_item,
    mine_shaft_at_player,
    set_gamemode,
    set_time,
    set_weather,
    summon_entity,
)


def _facing_replies(x: int, y: int, z: int, yaw: float):
    return [
        f"JavaTester has the following entity data: [{x}.5d, {y}.0d, {z}.5d]",
        f"JavaTester has the following entity data: [{yaw}f, 0.0f]",
    ]


def test_execute_tool_dry_run():
    r = execute_tool(
        "build_platform",
        {
            "center_x": 0,
            "y": 80,
            "center_z": 0,
            "width": 5,
            "depth": 5,
            "block": "quartz_block",
        },
        dry_run=True,
    )
    assert r.ok
    assert "dry-run" in r.output


def test_volume_guard_math():
    assert _volume(Vec3(0, 0, 0), Vec3(9, 9, 9)) == 1000


def test_unknown_tool():
    r = execute_tool("not_a_tool", {}, dry_run=True)
    assert not r.ok


def _captured_rcon(replies):
    calls: list[str] = []

    def fake(cmd, timeout=30):
        calls.append(cmd)
        return replies.pop(0) if replies else "OK"

    return calls, fake


def test_mine_shaft_drills_downward_one_wide():
    calls, fake = _captured_rcon(["Successfully filled 100 block(s)"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = mine_shaft_at_player("JavaTester", depth=100)
    assert r.ok, r.error
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd.startswith("execute as JavaTester at @s run fill ")
    # 1-wide column: radius 0 → ~0..~0 on x/z, ~-1 down to ~-100 on y
    assert "~ ~-1 ~ ~ ~-100 ~ air replace" in cmd
    assert r.block_estimate == 100


def test_mine_shaft_respects_forward_offset_and_radius():
    calls, fake = _captured_rcon(["Successfully filled 50 block(s)"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = mine_shaft_at_player("JavaTester", depth=50, radius=1, forward_offset=1)
    assert r.ok
    cmd = calls[0]
    assert "positioned ^ ^ ^1" in cmd
    assert "~-1 ~-1 ~-1 ~1 ~-50 ~1 air replace" in cmd
    assert r.block_estimate == 9 * 50  # (2*1+1)^2 * depth


def test_mine_shaft_clamps_extreme_inputs():
    calls, fake = _captured_rcon(["OK"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = mine_shaft_at_player("JavaTester", depth=10_000, radius=99, forward_offset=999)
    assert r.ok
    cmd = calls[0]
    # depth capped at 256, radius capped at 5, forward_offset capped at 16
    assert "positioned ^ ^ ^16" in cmd
    assert "~-5 ~-1 ~-5 ~5 ~-256 ~5 air replace" in cmd


def test_build_house_creates_door_and_windows():
    calls, fake = _captured_rcon(["OK"] * 9)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_house(100, 80, 200)
    assert r.ok, r.error
    joined = "\n".join(calls)
    assert "oak_door[facing=north,half=lower]" in joined
    assert "oak_door[facing=north,half=upper]" in joined
    assert joined.count("glass_pane") == 2
    assert calls[0].startswith("fill 97 80 197 103 84 203 oak_planks hollow")


def test_set_time_normalizes_aliases():
    calls, fake = _captured_rcon(["Set the time to 1000"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = set_time("morning")
    assert r.ok
    assert calls == ["time set day"]


def test_set_weather_normalizes_aliases():
    calls, fake = _captured_rcon(["Changed the weather to clear"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = set_weather("sunny")
    assert r.ok
    assert calls == ["weather clear"]


def test_set_gamemode_accepts_short_alias():
    calls, fake = _captured_rcon(["Set JavaTester's gamemode to Creative Mode"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = set_gamemode("JavaTester", "c")
    assert r.ok
    assert calls == ["gamemode creative JavaTester"]


def test_give_haste_uses_seconds_not_ticks():
    calls, fake = _captured_rcon(["Given [Haste II] to JavaTester for 600 seconds"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = give_haste("JavaTester", duration_sec=600, amplifier=2)
    assert r.ok
    assert calls == ["effect give JavaTester haste 600 2"]


def test_fawe_wrappers_validate_bounds():
    bad_sphere = fawe_sphere_at_player("JavaTester", "glass", 0)
    bad_cyl = fawe_cyl_at_player("JavaTester", "stone", radius=2, height=999)
    assert not bad_sphere.ok
    assert not bad_cyl.ok


def test_build_bridge_at_player_extends_forward_when_facing_south():
    # yaw 0 = facing south (+Z); player's right is west (-X)
    replies = _facing_replies(100, 80, 200, 0.0) + ["Successfully filled 24 block(s)"]
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_bridge_at_player("JavaTester", length=12, width=2, block="oak_planks")
    assert r.ok, r.error
    fill_cmd = [c for c in calls if c.startswith("fill ")][0]
    # deck at player_y - 1 = 79, spans z=201..212, x={99,100} (player at right edge)
    assert "fill 99 79 201 100 79 212 oak_planks replace" == fill_cmd


def test_build_bridge_at_player_west_facing():
    # yaw 90 = facing west (-X)
    replies = _facing_replies(50, 64, 50, 90.0) + ["Successfully filled 10 block(s)"]
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_bridge_at_player("JavaTester", length=10, width=1, block="cobblestone")
    assert r.ok
    fill_cmd = [c for c in calls if c.startswith("fill ")][0]
    assert "fill 40 63 50 49 63 50 cobblestone replace" == fill_cmd


def test_build_house_at_player_places_house_in_front_with_door_facing_player():
    # yaw 0 = south, so house extends +Z and door faces north (back to player)
    replies = _facing_replies(0, 80, 0, 0.0) + ["OK"] * 9
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_house_at_player("JavaTester", width=7, depth=7, height=5, distance=3)
    assert r.ok, r.error
    joined = "\n".join(calls)
    # house center 3 + 7//2 = 6 forward of player (+Z)
    assert "fill -3 79 3 3 83 9 oak_planks hollow" in joined
    # door faces back toward the player (south facing → north door)
    assert "oak_door[facing=north,half=lower]" in joined


def test_build_wall_at_player_perpendicular_to_facing():
    # yaw 180 = facing north (-Z), wall spans X
    replies = _facing_replies(20, 70, 30, 180.0) + ["Successfully filled 32 block(s)"]
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_wall_at_player("JavaTester", length=8, height=4, block="stone_bricks", distance=2)
    assert r.ok
    fill_cmd = [c for c in calls if c.startswith("fill ")][0]
    # 2 in front along -Z → z = 28. Wall spans X centered at 20 (half=3, extra=4).
    assert "fill 17 70 28 24 73 28 stone_bricks replace" == fill_cmd


# --- give_item ----------------------------------------------------------


def test_normalize_item_id_strips_namespace_and_aliases():
    assert _normalize_item_id("minecraft:diamond_pickaxe") == "diamond_pickaxe"
    assert _normalize_item_id("Pickaxe") == "diamond_pickaxe"
    assert _normalize_item_id("sword") == "diamond_sword"
    assert _normalize_item_id("armor") == "diamond_chestplate"
    # already-canonical id stays unchanged
    assert _normalize_item_id("oak_planks") == "oak_planks"
    # plural → singular alias
    assert _normalize_item_id("torches") == "torch"


def test_give_item_runs_vanilla_give_with_clamped_count():
    calls, fake = _captured_rcon(["Gave 1 [Diamond Pickaxe] to JavaTester"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = give_item("JavaTester", "pickaxe", count=99)
    assert r.ok, r.error
    assert calls == ["give JavaTester diamond_pickaxe 64"]
    assert r.block_estimate == 64


def test_give_item_respects_components_string():
    calls, fake = _captured_rcon(["Gave 1 [Diamond Sword] to JavaTester"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = give_item(
            "JavaTester",
            "diamond_sword",
            count=1,
            components="[minecraft:enchantments={\"minecraft:sharpness\":5}]",
        )
    assert r.ok
    assert calls == [
        'give JavaTester diamond_sword[minecraft:enchantments={"minecraft:sharpness":5}] 1'
    ]


def test_give_item_refuses_denylisted_items():
    r = give_item("JavaTester", "command_block")
    assert not r.ok
    assert "command_block" in r.error


def test_give_item_surfaces_rcon_error_text():
    calls, fake = _captured_rcon(["Unknown item 'minecraft:bogus_item'"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = give_item("JavaTester", "bogus_item")
    assert not r.ok
    assert "Unknown item" in r.output


# --- build_castle_at_player ---------------------------------------------


def test_build_castle_at_player_produces_hollow_walls_and_towers():
    # yaw 0 → facing south (+Z); castle extends +Z from the player.
    replies = _facing_replies(0, 80, 0, 0.0) + ["Successfully filled blocks(s)"] * 200
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_castle_at_player(
            "JavaTester",
            size=11,
            height=6,
            tower_height=10,
            tower_size=3,
            distance=3,
        )
    assert r.ok, r.error
    joined = "\n".join(calls)
    # Outer walls are HOLLOW, not solid (the core bug we are fixing).
    assert " stone_bricks hollow" in joined
    # No replace-mode 3D mass fill at castle scale (would make it solid).
    # Single-layer floors and 1x1 restored corner columns are intentional.
    solid_mass_fills = []
    for c in calls:
        if not (c.startswith("fill ") and c.endswith(" stone_bricks replace")):
            continue
        parts = c.split()
        x1, y1, z1, x2, y2, z2 = map(int, parts[1:7])
        spans_x = abs(x2 - x1) + 1
        spans_y = abs(y2 - y1) + 1
        spans_z = abs(z2 - z1) + 1
        if spans_x > 1 and spans_y > 1 and spans_z > 1:
            solid_mass_fills.append(c)
    assert solid_mass_fills == []
    # Crenelations: setblock entries along the wall top
    cren = [c for c in calls if c.startswith("setblock ") and "stone_bricks" in c]
    assert len(cren) >= 8
    # Doorway: 2-block air opening + paired door (lower+upper) facing player.
    assert any(
        c.endswith("oak_door[facing=north,half=lower]") for c in calls
    ), joined
    assert any(
        c.endswith("oak_door[facing=north,half=upper]") for c in calls
    )
    # Towers: 4 hollow tower fills (one per corner).
    tower_fills = [c for c in calls if "hollow" in c and "fill " in c]
    # 1 wall + 4 towers = 5 hollow fills.
    assert len(tower_fills) == 5


# --- summon_entity ------------------------------------------------------


def test_normalize_entity_handles_plurals_and_namespace():
    assert _normalize_entity_id("chickens") == "chicken"
    assert _normalize_entity_id("Bunnies") == "rabbit"
    assert _normalize_entity_id("minecraft:cow") == "cow"
    assert _normalize_entity_id(" Sheep ") == "sheep"


def test_summon_entity_runs_n_summons_clamped_to_32():
    calls, fake = _captured_rcon(["OK"] * 99)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = summon_entity("chickens", 10, 64, 20, count=99)
    assert r.ok, r.error
    assert len(calls) == 32
    assert calls[0] == "summon chicken 10 64 20"


def test_summon_entity_allows_bosses():
    calls, fake = _captured_rcon(["OK"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = summon_entity("wither", 0, 64, 0)
    assert r.ok, r.error
    assert calls == ["summon wither 0 64 0"]


def test_summon_entity_normalizes_ender_dragon():
    calls, fake = _captured_rcon(["OK"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = summon_entity("ender dragon", 1, 70, 2)
    assert r.ok, r.error
    assert calls == ["summon ender_dragon 1 70 2"]


def test_summon_entity_appends_nbt_when_provided():
    calls, fake = _captured_rcon(["OK"])
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = summon_entity("villager", 1, 2, 3, count=1, nbt="{NoAI:1b}")
    assert r.ok, r.error
    assert calls[0] == "summon villager 1 2 3 {NoAI:1b}"


# --- build_animal_pen_at_player -----------------------------------------


def test_build_animal_pen_open_air_has_fence_and_animals():
    # yaw 0 → facing south (+Z); pen extends in front of the player.
    replies = _facing_replies(0, 80, 0, 0.0) + ["OK"] * 99
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_animal_pen_at_player(
            "JavaTester",
            animal="chicken",
            count=4,
            width=5,
            depth=5,
            distance=3,
        )
    assert r.ok, r.error
    joined = "\n".join(calls)
    # Floor laid first
    assert any("fill " in c and " grass_block replace" in c for c in calls)
    # Four explicit fence sides, not one-block-tall `hollow` (which fills
    # the whole pen with fence posts in vanilla /fill semantics).
    fence_fills = [
        c
        for c in calls
        if c.startswith("fill ") and c.endswith(" oak_fence replace")
    ]
    assert len(fence_fills) == 4, joined
    assert not any(" oak_fence hollow" in c for c in calls), joined
    # Fence gate facing back toward player (north → player is at -Z relative
    # to the pen, so the gate sits on the near edge).
    assert any(
        c.startswith("setblock ") and "oak_fence_gate[facing=north]" in c
        for c in calls
    ), joined
    # 4 chickens summoned inside
    summons = [c for c in calls if c.startswith("summon chicken ")]
    assert len(summons) == 4
    # No wall_block / oak_planks (open pen, no roof).
    assert not any("oak_planks" in c for c in calls)


def test_build_animal_pen_with_roof_adds_walls_and_door():
    replies = _facing_replies(0, 80, 0, 0.0) + ["OK"] * 99
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_animal_pen_at_player(
            "JavaTester",
            animal="chicken",
            count=2,
            width=5,
            depth=5,
            distance=2,
            with_roof=True,
        )
    assert r.ok, r.error
    joined = "\n".join(calls)
    # Plank walls (hollow) + slab roof present
    assert any(" oak_planks hollow" in c for c in calls), joined
    assert any(" oak_slab replace" in c for c in calls), joined
    # Door pair facing the player carved into the front wall
    assert any(
        c.endswith("oak_door[facing=north,half=lower]") for c in calls
    ), joined
    assert any(
        c.endswith("oak_door[facing=north,half=upper]") for c in calls
    ), joined
    # 2 chickens summoned
    assert sum(1 for c in calls if c.startswith("summon chicken ")) == 2


def test_build_animal_pen_rejects_hostile_or_unknown_animal():
    replies = _facing_replies(0, 80, 0, 0.0)
    _, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_animal_pen_at_player("JavaTester", animal="zombie", count=4)
    assert not r.ok
    assert "zombie" in (r.error or "")


def test_build_animal_pen_clamps_counts_and_size():
    replies = _facing_replies(0, 80, 0, 0.0) + ["OK"] * 200
    calls, fake = _captured_rcon(replies)
    with patch("agent.tools._monolith._rcon", side_effect=fake):
        r = build_animal_pen_at_player(
            "JavaTester",
            animal="cow",
            count=99,
            width=99,
            depth=99,
            distance=99,
        )
    assert r.ok, r.error
    summons = [c for c in calls if c.startswith("summon cow ")]
    assert len(summons) == 16
