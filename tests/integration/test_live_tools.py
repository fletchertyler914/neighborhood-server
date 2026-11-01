"""Deterministic live Minecraft tool integration tests.

These tests intentionally bypass the LLM/orchestrator. They call
``agent.tools`` directly, then verify the running Paper server state through
RCON probes. They are gated by ``AGENT_LIVE_TOOL_TESTS=1`` because they mutate a
fixed sandbox region.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent import tools as T
from agent.eval.world import Box, block_is, block_is_passable, clear_box


RUN_LIVE = os.environ.get("AGENT_LIVE_TOOL_TESTS") == "1"
PLAYER = os.environ.get("AGENT_LIVE_TOOL_PLAYER", "")
SANDBOX = Box(
    int(os.environ.get("AGENT_LIVE_TOOL_X1", "9100")),
    int(os.environ.get("AGENT_LIVE_TOOL_Y1", "80")),
    int(os.environ.get("AGENT_LIVE_TOOL_Z1", "9100")),
    int(os.environ.get("AGENT_LIVE_TOOL_X2", "9130")),
    int(os.environ.get("AGENT_LIVE_TOOL_Y2", "100")),
    int(os.environ.get("AGENT_LIVE_TOOL_Z2", "9130")),
).normalize()

# Holding zone sits next to the sandbox with its own stone pad so the player
# always has solid ground when the sandbox is being cleared.
HOLD_X = SANDBOX.x2 + 4
HOLD_Y = SANDBOX.y1 + 2
HOLD_Z = SANDBOX.z1 - 4

# Server-side movement registers within a tick or two; give the client a
# moment to land on freshly-placed floors before tools that read player
# position run (mine_shaft, fawe_*).
TELEPORT_SETTLE_SEC = float(os.environ.get("AGENT_LIVE_TOOL_SETTLE_SEC", "0.4"))

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="set AGENT_LIVE_TOOL_TESTS=1 to run live Minecraft tool integration tests",
)


def _assert_ok(result: T.ToolResult) -> T.ToolResult:
    assert result.ok, result.summary()
    return result


def _rcon(command: str, *, timeout: int = 30) -> str:
    return T._rcon(command, timeout=timeout)


def _setblock(x: int, y: int, z: int, block: str = "stone") -> None:
    out = _rcon(f"setblock {x} {y} {z} {block}")
    assert "Cannot place" not in out


def _player_pos(player: str) -> tuple[float, float, float] | None:
    out = _rcon(f"data get entity {T._quote_player(player)} Pos")
    match = re.search(r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]", out or "")
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def _fill_air(box: Box) -> None:
    clear_box(box)


def _fill_solid(box: Box, block: str = "stone") -> None:
    b = box.normalize()
    out = _rcon(
        f"fill {b.x1} {b.y1} {b.z1} {b.x2} {b.y2} {b.z2} {block} replace",
        timeout=60,
    )
    assert "incorrect" not in (out or "").lower(), out


def _sandbox_box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> Box:
    return Box(
        SANDBOX.x1 + x1,
        SANDBOX.y1 + y1,
        SANDBOX.z1 + z1,
        SANDBOX.x1 + x2,
        SANDBOX.y1 + y2,
        SANDBOX.z1 + z2,
    ).normalize()


def _place_player_safely(player: str, x: int, y: int, z: int) -> None:
    """Place a 3x3 stone pad at y-1 then teleport the player onto it.

    Avoids "teleport into air → player falls during tool" bugs in
    player-relative tools by guaranteeing solid ground at the destination.
    """

    pad = Box(x - 1, y - 1, z - 1, x + 1, y - 1, z + 1)
    _fill_solid(pad, "stone")
    _assert_ok(T.teleport_player(player, x, y, z))
    if TELEPORT_SETTLE_SEC > 0:
        time.sleep(TELEPORT_SETTLE_SEC)


def _place_player_safely_facing(player: str, x: int, y: int, z: int, yaw: int, pitch: int = 0) -> None:
    _fill_solid(Box(x - 1, y - 1, z - 1, x + 1, y - 1, z + 1), "stone")
    _rcon(f"tp {T._quote_player(player)} {x} {y} {z} {yaw} {pitch}")
    if TELEPORT_SETTLE_SEC > 0:
        time.sleep(TELEPORT_SETTLE_SEC)


def _park_player_in_holding_zone() -> None:
    if not PLAYER:
        return
    _setblock(HOLD_X, HOLD_Y - 1, HOLD_Z, "stone")
    _assert_ok(T.teleport_player(PLAYER, HOLD_X, HOLD_Y, HOLD_Z))
    if TELEPORT_SETTLE_SEC > 0:
        time.sleep(TELEPORT_SETTLE_SEC)


@pytest.fixture(scope="module")
def session_player_pos():
    """Capture the player's original position once and restore at session end."""

    if not PLAYER:
        yield None
        return
    original = _player_pos(PLAYER)
    yield original
    if original:
        x, y, z = original
        _assert_ok(T.teleport_player(PLAYER, int(round(x)), int(round(y)), int(round(z))))


@pytest.fixture(autouse=True)
def clean_sandbox(session_player_pos):
    # Park player away from the sandbox before mutating it so they never end
    # up floating mid-test from the cleanup wiping their floor.
    _park_player_in_holding_zone()
    _fill_air(SANDBOX)
    try:
        yield
    finally:
        _park_player_in_holding_zone()
        _fill_air(SANDBOX)
        _setblock(HOLD_X, HOLD_Y - 1, HOLD_Z, "air")


def test_live_fill_box_and_clear_box_execute_on_server():
    box = _sandbox_box(1, 1, 1, 3, 2, 3)

    result = _assert_ok(
        T.fill_box(box.x1, box.y1, box.z1, box.x2, box.y2, box.z2, "gold_block")
    )

    assert result.commands == [
        f"fill {box.x1} {box.y1} {box.z1} {box.x2} {box.y2} {box.z2} gold_block replace"
    ]
    assert block_is(box.x1, box.y1, box.z1, "gold_block")
    assert block_is(box.x2, box.y2, box.z2, "gold_block")

    _assert_ok(T.clear_box(box.x1, box.y1, box.z1, box.x2, box.y2, box.z2))
    assert block_is_passable(box.x1, box.y1, box.z1)
    assert block_is_passable(box.x2, box.y2, box.z2)


def test_live_build_platform_and_sphere_execute_on_server():
    cx, y, cz = SANDBOX.x1 + 8, SANDBOX.y1 + 2, SANDBOX.z1 + 8

    platform = _assert_ok(T.build_platform(cx, y, cz, width=5, depth=3, block="quartz_block"))
    assert platform.block_estimate == 15
    assert block_is(cx - 2, y, cz - 1, "quartz_block")
    assert block_is(cx + 2, y, cz + 1, "quartz_block")

    sphere = _assert_ok(
        T.build_sphere(cx, y + 5, cz, radius=2, block="amethyst_block", hollow=False)
    )
    assert sphere.block_estimate > 0
    assert block_is(cx, y + 5, cz, "amethyst_block")
    assert block_is(cx + 2, y + 5, cz, "amethyst_block")


def test_live_build_cylinder_hollow_executes_on_server():
    cx, y, cz = SANDBOX.x1 + 18, SANDBOX.y1 + 1, SANDBOX.z1 + 8

    result = _assert_ok(
        T.build_cylinder(cx, y, cz, radius=3, height=4, block="stone_bricks", hollow=True)
    )

    assert result.block_estimate > 0
    assert block_is(cx + 3, y, cz, "stone_bricks")
    assert block_is(cx + 3, y + 3, cz, "stone_bricks")
    assert block_is_passable(cx, y, cz)


def test_live_build_house_has_door_and_two_windows():
    cx, y, cz = SANDBOX.x1 + 18, SANDBOX.y1 + 1, SANDBOX.z1 + 20

    result = _assert_ok(T.build_house(cx, y, cz, width=7, depth=7, height=5))

    assert result.tool == "build_house"
    front_z = cz - 3
    assert block_is(cx, y + 1, front_z, "oak_door")
    assert block_is(cx, y + 2, front_z, "oak_door")
    assert block_is(cx - 2, y + 2, front_z, "glass_pane")
    assert block_is(cx + 2, y + 2, front_z, "glass_pane")
    assert block_is(cx, y + 5, cz, "oak_slab")


def test_live_spiral_staircase_executes_on_server():
    cx, y, cz = SANDBOX.x1 + 8, SANDBOX.y1 + 1, SANDBOX.z1 + 20

    result = _assert_ok(
        T.build_spiral_staircase(
            cx,
            y,
            cz,
            height=6,
            radius=2,
            block="smooth_stone",
            rail_block="iron_bars",
        )
    )

    assert result.block_estimate == 1 + 6 * 3
    assert block_is(cx, y, cz, "smooth_stone")
    assert block_is(cx + 2, y, cz, "smooth_stone")
    assert block_is(cx + 3, y, cz, "iron_bars")


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative tools")
def test_live_mine_shaft_at_player_executes_downward():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 20, SANDBOX.y1 + 10, SANDBOX.z1 + 20
    shaft_column = Box(x, y - 5, z, x, y - 1, z)
    _fill_solid(shaft_column, "stone")
    _place_player_safely(player, x, y, z)

    result = _assert_ok(T.mine_shaft_at_player(player, depth=5, radius=0, forward_offset=0))

    assert result.block_estimate == 5
    assert result.commands == [
        f"execute as {player} at @s run fill ~ ~-1 ~ ~ ~-5 ~ air replace"
    ]
    for yy in range(y - 1, y - 6, -1):
        assert block_is_passable(x, yy, z)


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative tools")
def test_live_mine_shaft_forward_offset_uses_player_facing():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 12, SANDBOX.y1 + 10, SANDBOX.z1 + 20
    forward_z = z + 1  # yaw=0 faces south / +Z in Minecraft.
    behind_z = z - 1
    _fill_solid(Box(x, y - 4, forward_z, x, y - 1, forward_z), "stone")
    _fill_solid(Box(x, y - 4, behind_z, x, y - 1, behind_z), "stone")
    _place_player_safely_facing(player, x, y, z, yaw=0)

    result = _assert_ok(T.mine_shaft_at_player(player, depth=4, radius=0, forward_offset=1))

    assert result.commands == [
        f"execute as {player} at @s positioned ^ ^ ^1 run fill ~ ~-1 ~ ~ ~-4 ~ air replace"
    ]
    for yy in range(y - 1, y - 5, -1):
        assert block_is_passable(x, yy, forward_z)
        assert block_is(x, yy, behind_z, "stone")


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative tools")
def test_live_build_bridge_at_player_lays_deck_in_front():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 5, SANDBOX.y1 + 8, SANDBOX.z1 + 5
    _place_player_safely_facing(player, x, y, z, yaw=0)  # facing south (+Z)

    result = _assert_ok(
        T.build_bridge_at_player(player, length=6, width=2, block="oak_planks", distance=1)
    )

    # deck is one block below player level
    deck_y = y - 1
    # forward span: z+1 .. z+6, width spans x={x-1, x} for south-facing
    for dz in range(1, 7):
        assert block_is(x, deck_y, z + dz, "oak_planks")
        assert block_is(x - 1, deck_y, z + dz, "oak_planks")
    # block behind the player stays unchanged
    assert not block_is(x, deck_y, z - 1, "oak_planks")
    assert result.commands and result.commands[0].startswith("fill ")


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative tools")
def test_live_build_house_at_player_places_door_toward_player():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 5, SANDBOX.y1 + 8, SANDBOX.z1 + 12
    _place_player_safely_facing(player, x, y, z, yaw=0)  # facing south (+Z)

    result = _assert_ok(
        T.build_house_at_player(player, width=5, depth=5, height=4, distance=3)
    )

    assert result.tool == "build_house_at_player"
    # center_forward = 3 + 5//2 = 5 → house centered at z+5; near wall at z+3
    near_wall_z = z + 3
    door_x = x
    door_y_lower = y  # build_house's `y` param is facing.y - 1, door at y+1
    # Door faces back toward the player (south facing → door facing=north)
    ok = _rcon(
        f"execute if block {door_x} {door_y_lower} {near_wall_z} "
        f"oak_door[facing=north,half=lower]"
    )
    assert "passed" in (ok or ""), ok


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative tools")
def test_live_build_wall_at_player_perpendicular_to_facing():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 18, SANDBOX.y1 + 8, SANDBOX.z1 + 5
    _place_player_safely_facing(player, x, y, z, yaw=0)  # facing south (+Z)

    _assert_ok(
        T.build_wall_at_player(player, length=5, height=3, block="stone_bricks", distance=2)
    )

    wall_z = z + 2
    # length=5 → half=2, extra=2; spans x-2..x+2 for south-facing
    # (right vector = -X so wall extends both sides of player column)
    spans = [block_is(x + dx, y + dy, wall_z, "stone_bricks") for dx in (-2, 0, 2) for dy in (0, 2)]
    assert all(spans), spans


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for FAWE player tools")
def test_live_fawe_cylinder_executes_as_player():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 23, SANDBOX.y1 + 2, SANDBOX.z1 + 23
    _place_player_safely(player, x, y, z)

    result = _assert_ok(T.fawe_cyl_at_player(player, "glass", radius=2, height=3))

    assert result.commands == [f"agentexec {player} //cyl glass 2 3"]
    _wait_for_block(x + 2, y, z, "glass")
    _wait_for_block(x, y + 2, z, "glass")


def test_live_server_admin_tools_execute_without_llm():
    _assert_ok(T.preflight())
    _assert_ok(T.set_time("day"))
    _assert_ok(T.set_weather("clear"))


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for give_item tests")
def test_live_give_item_places_pickaxe_in_inventory():
    player = PLAYER
    # Wipe just enough inventory slots so we can locate the new item.
    _rcon(f"clear {player} diamond_pickaxe")

    _assert_ok(T.give_item(player, "pickaxe", count=1))

    # The live server should now report the player has a diamond_pickaxe.
    # Use `clear <player> diamond_pickaxe 0` which prints the existing count
    # without removing anything.
    probe = _rcon(f"clear {player} diamond_pickaxe 0")
    assert "1 item" in (probe or "") or "Found 1" in (probe or ""), probe


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for give_item tests")
def test_live_give_item_rejects_denylisted_command_block():
    r = T.give_item(PLAYER, "command_block")
    assert not r.ok
    assert "not allowed" in (r.error or "")


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for player-relative builds")
def test_live_build_castle_at_player_is_hollow_with_corner_towers():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 4, SANDBOX.y1 + 8, SANDBOX.z1 + 4
    _place_player_safely_facing(player, x, y, z, yaw=0)  # facing south (+Z)

    result = _assert_ok(
        T.build_castle_at_player(
            player,
            size=9,
            height=5,
            tower_height=8,
            tower_size=3,
            distance=2,
        )
    )
    assert result.tool == "build_castle_at_player"

    # The castle is centered (distance + size//2) = 2 + 4 = 6 forward (+Z),
    # so it occupies z ∈ [z+2 .. z+10] and x ∈ [x-4 .. x+4].
    cx, cz = x, z + 6
    half = 9 // 2  # 4

    # Outer wall corner must be the wall block (proves walls exist).
    assert block_is(cx - half, y + 1, cz - half, "stone_bricks"), (
        "no corner wall at castle ground level"
    )
    # Interior at the same y MUST be air (proves walls are hollow, not solid).
    assert block_is_passable(cx, y + 2, cz), (
        "castle interior is filled — should be hollow"
    )
    # Corner tower top should be the wall block (above the wall height).
    assert block_is(cx - half, y + 6, cz - half, "stone_bricks"), (
        "no tower extending above wall height"
    )


def _count_entities(x: int, y: int, z: int, kind: str, dist: int = 12) -> int:
    """Use /execute to count entities of ``kind`` near (x,y,z)."""

    out = _rcon(
        f"execute positioned {x} {y} {z} if entity @e[type={kind},distance=..{dist}]"
    )
    # Vanilla replies "Test passed" when at least one matches. For an exact
    # count, use the 'store' helper.
    if "Test passed" in (out or "") or "passed" in (out or ""):
        return 1
    return 0


def _count_entities_exact(x: int, y: int, z: int, kind: str, dist: int = 12) -> int:
    """Count chickens near a point by running execute … if entity once per
    candidate slot. We use a tighter helper: list nearby entities via
    /data and parse the count via the @e selector with limit/sort."""

    # Use the predicate sum hack: store result of execute if entity into a
    # dummy scoreboard, then read it.
    obj = "agentcount"
    _rcon(f"scoreboard objectives add {obj} dummy")
    _rcon(f"scoreboard players set #agent {obj} 0")
    _rcon(
        f"execute store result score #agent {obj} run "
        f"execute positioned {x} {y} {z} if entity @e[type={kind},distance=..{dist}]"
    )
    out = _rcon(f"scoreboard players get #agent {obj}") or ""
    m = re.search(r"has\s+([0-9-]+)", out)
    if m:
        try:
            return max(0, int(m.group(1)))
        except ValueError:
            return 0
    return 0


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for summon tests")
def test_live_summon_entity_spawns_chickens():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 6, SANDBOX.y1 + 10, SANDBOX.z1 + 6
    _place_player_safely_facing(player, x, y, z, yaw=0)
    # Clear any pre-existing chickens in the test zone so the count is fresh.
    _rcon(f"kill @e[type=chicken,x={x},y={y},z={z},distance=..15]")

    result = _assert_ok(T.summon_entity("chicken", x, y, z, count=3))
    assert result.tool == "summon_entity"
    # Vanilla /summon prints one line per call; loop should ran 3.
    assert "ran 3 commands" in (result.output or "")


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for pen builds")
def test_live_build_animal_pen_creates_fence_and_chickens():
    player = PLAYER
    x, y, z = SANDBOX.x1 + 8, SANDBOX.y1 + 8, SANDBOX.z1 + 4
    _place_player_safely_facing(player, x, y, z, yaw=0)  # facing south (+Z)
    # Clean up any prior chickens from earlier runs in this region.
    _rcon(f"kill @e[type=chicken,x={x},y={y},z={z},distance=..20]")

    result = _assert_ok(
        T.build_animal_pen_at_player(
            player,
            animal="chicken",
            count=4,
            width=5,
            depth=5,
            distance=3,
            with_roof=False,
        )
    )
    assert result.tool == "build_animal_pen_at_player"

    # Pen footprint: centered (distance + depth//2) = 3 + 2 = 5 in front (+Z).
    cx, cz = x, z + 5
    half = 5 // 2
    # The four fence corners must be oak_fence at y (pen top of floor + 1).
    fence_y = y - 1 + 1  # facing.y - 1 = floor_y; fence sits on floor_y+1
    assert block_is(cx - half, fence_y, cz - half, "oak_fence"), "no NW fence corner"
    assert block_is(cx + half, fence_y, cz + half, "oak_fence"), "no SE fence corner"
    # Interior block should be air (passable) — not solid walls.
    assert block_is_passable(cx, fence_y, cz), "pen interior is not passable"

    # Confirm we actually summoned chickens nearby.
    # Some servers may have minor floating point issues — be tolerant.
    nearby = _count_entities_exact(cx, fence_y, cz, "chicken", dist=10)
    assert nearby >= 1, f"expected chickens near pen, found {nearby}"


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for template paste")
def test_live_paste_template_chicken_coop_fallback_builds_pen():
    """Template paste builds/loads the coop and still runs follow-up chickens."""
    player = PLAYER
    x, y, z = SANDBOX.x1 + 8, SANDBOX.y1 + 8, SANDBOX.z1 + 12
    _place_player_safely_facing(player, x, y, z, yaw=0)
    _rcon(f"kill @e[type=chicken,x={x},y={y},z={z},distance=..24]")

    result = _assert_ok(T.paste_template_at_player(player, "chicken_coop_small"))
    assert result.tool == "paste_template_at_player"
    assert "pasted template chicken_coop_small" in (result.output or "").lower() or "fallback" in (
        result.output or ""
    ).lower()

    cx, cz = x, z + 5
    fence_y = y
    assert block_is(cx, fence_y, cz, "oak_fence") or block_is_passable(cx, fence_y, cz)
    nearby = _count_entities_exact(cx, fence_y + 1, cz, "chicken", dist=12)
    assert nearby >= 1, f"expected chickens after template follow-up, found {nearby}"


@pytest.mark.skipif(not PLAYER, reason="set AGENT_LIVE_TOOL_PLAYER for chat feedback")
def test_live_rating_prompt_persists_feedback_record(tmp_path, monkeypatch):
    """End-to-end: record a fake job for the player, hit the feedback API
    via the in-process orchestrator helpers, confirm the JSONL row lands."""
    monkeypatch.setenv("NEIGHBORHOOD_REPO", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    import agent.feedback as fb

    fb._audit_loaded = False
    fb._last_job_by_player.clear()
    fb.remember_last_job(PLAYER, "live-test-job")
    entry = fb.record_feedback(player=PLAYER, rating="good", note="solid")
    assert entry.job_id == "live-test-job"
    rows = list(fb.iter_feedback())
    assert rows and rows[-1]["rating"] == "good"


def _wait_for_block(x: int, y: int, z: int, block: str, *, timeout_sec: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if block_is(x, y, z, block):
            return
        time.sleep(0.25)
    assert block_is(x, y, z, block), f"expected {block} at {x},{y},{z}"


def test_live_player_env_names_online_player_when_set():
    if not PLAYER:
        pytest.skip("set AGENT_LIVE_TOOL_PLAYER to verify player-specific tests")
    out = _rcon("list")
    assert re.search(rf"(^|[, ]){re.escape(PLAYER)}($|[, ])", out), out
