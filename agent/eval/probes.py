"""World-state probes for corpus eval (RCON-backed)."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Any

from agent.eval.corpus_case import WorldProbe
from agent.eval.world import (
    Box,
    block_is,
    block_is_passable,
    rcon,
    _player_pos,
)
from agent import tools as T
from agent.world_auditor.hash import content_hash
from agent.world_auditor.invariants import verify_structure
from agent.world_auditor.snapshot import SnapshotBox, snapshot_box

_PASTE_ANCHOR_RE = re.compile(
    r"pasted template .+ at \((-?\d+),\s*(-?\d+),\s*(-?\d+)\)", re.IGNORECASE
)
_TP_COMMAND_RE = re.compile(
    r"\btp\s+\S+\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\b", re.IGNORECASE
)
_FILL_COMMAND_RE = re.compile(
    r"\bfill\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\b",
    re.IGNORECASE,
)


def _anchor_from_commands(commands: list[Any] | None) -> tuple[int, int, int] | None:
    """Parse the build anchor from a tool's emitted command list.

    Supports two patterns:

    1. `paste_template_at_player`-style: first command is
       ``tp <player> <x> <y> <z>`` placing the player at the paste origin.
    2. Parametric `build_*_at_player` tools: first command is a ``fill x1 y1
       z1 x2 y2 z2 ...`` covering the build footprint; we return the midpoint.
    """

    if not commands:
        return None
    for entry in commands:
        text = str(entry or "")
        m = _TP_COMMAND_RE.search(text)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = _FILL_COMMAND_RE.search(text)
        if m:
            x1, y1, z1, x2, y2, z2 = (int(g) for g in m.groups())
            return (x1 + x2) // 2, min(y1, y2), (z1 + z2) // 2
    return None
_NATURAL_BLOCKS = frozenset(
    {
        "air",
        "cave_air",
        "void_air",
        "grass_block",
        "dirt",
        "coarse_dirt",
        "podzol",
        "stone",
        "deepslate",
        "bedrock",
        "water",
        "lava",
    }
)


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str
    details: dict[str, Any] | None = None


def _normalize_block(block: str) -> str:
    s = (block or "").strip()
    if not s:
        return ""
    return s if ":" in s else f"minecraft:{s}"


def _strip_namespace(block: str) -> str:
    b = _normalize_block(block)
    return b.split(":")[-1] if b else ""


def player_forward_anchor(player: str, *, distance: int = 6) -> tuple[int, int, int] | None:
    """Approximate build anchor in front of player (south-facing sandbox default)."""

    pos = _player_pos(player)
    if pos is None:
        return None
    px, py, pz = pos
    try:
        facing = T._player_facing(player)
        if facing is None:
            return px, py - 1, pz + distance
        center_forward = distance
        ax = facing.x + facing.forward_dx * center_forward
        ay = facing.y - 1
        az = facing.z + facing.forward_dz * center_forward
        return int(ax), int(ay), int(az)
    except Exception:
        return px, py - 1, pz + distance


def infer_build_anchor_from_trace(
    tool_calls: list[dict[str, Any]] | None,
    *,
    player: str,
    sandbox_center: tuple[int, int, int],
    probe: WorldProbe | None,
) -> tuple[int, int, int] | None:
    """Parse paste/build coordinates from successful tool output."""

    for tc in tool_calls or []:
        result = tc.get("result") or {}
        if not result.get("ok"):
            continue
        output = str(result.get("output") or "")
        m = _PASTE_ANCHOR_RE.search(output)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        commands = result.get("commands") if isinstance(result.get("commands"), list) else None
        cmd_anchor = _anchor_from_commands(commands)
        if cmd_anchor is not None and tc.get("name") in {
            "paste_template_at_player",
            "build_house_at_player",
            "build_castle_at_player",
            "build_animal_pen_at_player",
            "build_bridge_at_player",
            "build_wall_at_player",
            "build_sphere",
            "build_cylinder",
            "build_platform",
            "fawe_sphere_at_player",
            "fawe_cyl_at_player",
        }:
            return cmd_anchor
        if tc.get("name") in {
            "build_house_at_player",
            "build_castle_at_player",
            "build_animal_pen_at_player",
            "build_sphere",
            "build_cylinder",
            "build_platform",
            "fawe_sphere_at_player",
            "fawe_cyl_at_player",
        }:
            args = tc.get("arguments") or {}
            if "center_x" in args:
                return int(args["center_x"]), int(args.get("y") or args.get("center_y") or 0), int(args["center_z"])
            facing = T._player_facing(player)
            if facing is None:
                continue
            width = int(args.get("width") or 7)
            depth = int(args.get("depth") or 7)
            distance = int(args.get("distance") or 3)
            center_forward = distance + max(depth, width) // 2
            ax = int(facing.x + facing.forward_dx * center_forward)
            az = int(facing.z + facing.forward_dz * center_forward)
            ay = int(facing.y - 1)
            return ax, ay, az
    return None


def resolve_anchor(
    probe: WorldProbe,
    *,
    player: str,
    sandbox_center: tuple[int, int, int],
    build_anchor: tuple[int, int, int] | None = None,
) -> tuple[int, int, int]:
    if build_anchor is not None:
        return build_anchor
    if probe.anchor == "player":
        pos = _player_pos(player)
        if pos:
            return pos
    if probe.anchor == "sandbox_center":
        return sandbox_center
    fwd = player_forward_anchor(player)
    if fwd:
        return fwd
    return sandbox_center


def _sample_offsets(n: int, radius: int) -> list[tuple[int, int, int]]:
    rng = random.Random(42)
    out: set[tuple[int, int, int]] = {(0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)}
    while len(out) < n:
        dx = rng.randint(-radius, radius)
        dy = rng.randint(0, max(1, radius // 2))
        dz = rng.randint(-radius, radius)
        out.add((dx, dy, dz))
    return list(out)[:n]


def _is_structure_block(x: int, y: int, z: int) -> bool:
    if block_is_passable(x, y, z):
        return False
    for natural in _NATURAL_BLOCKS:
        if block_is(x, y, z, natural):
            return False
    return True


def probe_template_built(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    blocks = probe.sample_blocks or []
    radius = max(3, probe.radius or 6)
    matches = 0
    checked = 0
    for dx, dy, dz in _sample_offsets(8, radius):
        x, y, z = anchor[0] + dx, anchor[1] + dy, anchor[2] + dz
        checked += 1
        if blocks:
            for block in blocks:
                if block_is(x, y, z, block):
                    matches += 1
                    break
        elif _is_structure_block(x, y, z):
            matches += 1
    ok = matches >= max(1, probe.min_matches)
    return ProbeResult(
        ok=ok,
        message=f"template_built: {matches}/{checked} samples matched structure",
        details={"matches": matches, "checked": checked, "anchor": anchor},
    )


def probe_shape_built(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    shape = probe.shape or "platform"
    block = probe.block or "quartz_block"
    block_norm = _strip_namespace(block)

    if shape == "platform":
        w = probe.width or 5
        d = probe.platform_depth or probe.width or 5
        matches = 0
        for dx in range(-w // 2, w // 2 + 1):
            for dz in range(-d // 2, d // 2 + 1):
                x, y, z = anchor[0] + dx, anchor[1], anchor[2] + dz
                out = rcon(f"execute if block {x} {y} {z} {_normalize_block(block)}")
                if "passed" in (out or "").lower():
                    matches += 1
        needed = max(3, (w * d) // 3)
        ok = matches >= needed
        return ProbeResult(
            ok=ok,
            message=f"platform: {matches} blocks matched (need>={needed})",
            details={"matches": matches, "needed": needed},
        )

    if shape == "cylinder":
        r = probe.radius or 4
        h = probe.height or 8
        hollow = bool(probe.hollow)
        shell_hits = 0
        interior_air = 0
        for angle_i in range(8):
            angle = (math.pi * 2 * angle_i) / 8
            sx = anchor[0] + int(round(r * math.cos(angle)))
            sz = anchor[2] + int(round(r * math.sin(angle)))
            for dy in range(h):
                out = rcon(
                    f"execute if block {sx} {anchor[1] + dy} {sz} {_normalize_block(block)}"
                )
                if "passed" in (out or "").lower():
                    shell_hits += 1
        if hollow:
            ix, iy, iz = anchor[0], anchor[1] + h // 2, anchor[2]
            interior_air = 1 if block_is_passable(ix, iy, iz) else 0
            ok = shell_hits >= 4 and interior_air >= 1
            msg = f"cylinder hollow: shell={shell_hits}, interior_air={interior_air}"
        else:
            ok = shell_hits >= 4
            msg = f"cylinder solid: shell={shell_hits}"
        return ProbeResult(ok=ok, message=msg, details={"shell_hits": shell_hits})

    if shape == "sphere":
        r = probe.radius or 5
        hits = 0
        for dx, dy, dz in _sample_offsets(8, r):
            x, y, z = anchor[0] + dx, anchor[1] + dy, anchor[2] + dz
            if block_is(x, y, z, block):
                hits += 1
        ok = hits >= max(2, probe.min_matches)
        return ProbeResult(ok=ok, message=f"sphere: {hits} sample hits", details={"hits": hits})

    return ProbeResult(ok=False, message=f"unknown shape {shape!r}")


def probe_mob_count(
    probe: WorldProbe,
    *,
    near: tuple[int, int, int],
) -> ProbeResult:
    entity = (probe.entity or "chicken").strip()
    if entity.startswith("minecraft:"):
        entity_type = entity
    else:
        entity_type = f"minecraft:{entity}"
    radius = max(1, probe.search_radius)
    x, y, z = near
    cmd = (
        f"execute positioned {x} {y} {z} run execute if entity "
        f"@e[type={entity_type},distance=..{radius},limit={max(probe.count_max or 32, probe.count_min + 1)}]"
    )
    out = rcon(cmd)
    present = "passed" in (out or "").lower()
    ok = present if probe.count_min >= 1 else True
    return ProbeResult(
        ok=ok,
        message=f"mob_count: {entity_type} within {radius} -> {present}",
        details={"present": present, "near": near},
    )


def probe_shaft_dug(
    probe: WorldProbe,
    *,
    player: str,
) -> ProbeResult:
    pos = _player_pos(player)
    if pos is None:
        return ProbeResult(ok=False, message="could not read player position")
    px, py, pz = pos
    depth = max(1, probe.shaft_depth or 8)
    air_count = 0
    for dy in range(1, depth + 1):
        if block_is_passable(px, py - dy, pz):
            air_count += 1
    ok = air_count >= max(1, depth // 2)
    return ProbeResult(
        ok=ok,
        message=f"shaft_dug: {air_count}/{depth} air below player",
        details={"air_count": air_count, "depth": depth},
    )


def probe_setting(
    probe: WorldProbe,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ProbeResult:
    setting = probe.setting
    value = (probe.value or "").lower()

    if tool_calls:
        for tc in tool_calls:
            if not (tc.get("result") or {}).get("ok"):
                continue
            name = tc.get("name") or ""
            if setting == "time" and name == "set_time":
                return ProbeResult(ok=True, message="time set via set_time tool")
            if setting == "weather" and name == "set_weather":
                return ProbeResult(ok=True, message="weather set via set_weather tool")
            if setting == "gamemode" and name == "set_gamemode":
                return ProbeResult(ok=True, message="gamemode set via set_gamemode tool")

    if setting == "time":
        out = rcon("time query day")
        m = re.search(r"(\d+)", out or "")
        if not m:
            return ProbeResult(ok=False, message=f"time day check: {out[:80]}")
        tick = int(m.group(1))
        if value in ("day", "noon", "morning"):
            ok = tick < 12000
            return ProbeResult(ok=ok, message=f"time day tick={tick}")
        if value == "night":
            ok = tick >= 13000
            return ProbeResult(ok=ok, message=f"time night tick={tick}")
    if setting == "weather":
        # Paper 1.21+ removed `weather query`; trust successful set_weather above.
        return ProbeResult(ok=False, message="weather probe unavailable without set_weather trace")
    if setting == "gamemode":
        return ProbeResult(ok=True, message="gamemode probe skipped (set via tool trace)")
    return ProbeResult(ok=False, message=f"unknown setting {setting!r}")


def probe_inventory_has(
    probe: WorldProbe,
    *,
    player: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ProbeResult:
    item = _strip_namespace(probe.item or "diamond_pickaxe")
    if tool_calls:
        for tc in tool_calls:
            if tc.get("name") != "give_item" or not (tc.get("result") or {}).get("ok"):
                continue
            args = tc.get("arguments") or {}
            got = _strip_namespace(str(args.get("item") or ""))
            if got == item or got in item or item in got:
                count = int(args.get("count") or 1)
                if count >= probe.min_count:
                    return ProbeResult(
                        ok=True,
                        message=f"inventory_has {item}: confirmed via give_item trace",
                    )
    out = rcon(f"data get entity {T._quote_player(player)} Inventory")
    if not out:
        return ProbeResult(ok=False, message="could not read inventory")
    pattern = rf'"{re.escape(item)}"'
    count = len(re.findall(pattern, out))
    ok = count >= probe.min_count
    return ProbeResult(
        ok=ok,
        message=f"inventory_has {item}: found~{count} need>={probe.min_count}",
        details={"count_estimate": count},
    )


def _auditor_box(probe: WorldProbe, anchor: tuple[int, int, int]) -> SnapshotBox:
    width = max(1, probe.bbox_width or probe.width or (probe.radius or 4) * 2 + 1)
    height = max(1, probe.bbox_height or probe.height or 6)
    depth = max(1, probe.bbox_depth or probe.platform_depth or probe.width or width)
    x1 = anchor[0] - width // 2
    z1 = anchor[2] - depth // 2
    return SnapshotBox(x1, anchor[1], z1, x1 + width - 1, anchor[1] + height - 1, z1 + depth - 1)


def _palette_of_interest(probe: WorldProbe) -> list[str]:
    """Block names probes care about, used to drive RCON ``execute if block`` checks."""

    blocks: list[str] = []
    if probe.block:
        blocks.append(probe.block)
    for k in (probe.min_counts or {}).keys():
        blocks.append(k)
    for k in (probe.max_counts or {}).keys():
        blocks.append(k)
    for raw in (probe.sample_blocks or []):
        blocks.append(raw)
    out: list[str] = []
    for raw in blocks:
        normalized = _normalize_block(raw)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def probe_palette_histogram(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    snap = snapshot_box(
        _auditor_box(probe, anchor),
        flush=True,
        include_sparse=False,
        palette_of_interest=_palette_of_interest(probe),
    )
    failures: list[str] = []
    for block, minimum in probe.min_counts.items():
        count = snap.palette.get(_normalize_block(block), 0)
        if count < minimum:
            failures.append(f"{block}={count}<min{minimum}")
    for block, maximum in probe.max_counts.items():
        count = snap.palette.get(_normalize_block(block), 0)
        if count > maximum:
            failures.append(f"{block}={count}>max{maximum}")
    ok = not failures
    return ProbeResult(
        ok=ok,
        message="palette_histogram ok" if ok else "; ".join(failures),
        details=snap.to_dict(),
    )


def probe_count_block_in_box(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    block = _normalize_block(probe.block or "air")
    snap = snapshot_box(
        _auditor_box(probe, anchor),
        flush=True,
        include_sparse=False,
        palette_of_interest=_palette_of_interest(probe),
    )
    count = snap.palette.get(block, 0)
    ok = count >= probe.min_count
    if probe.count_max is not None:
        ok = ok and count <= probe.count_max
    return ProbeResult(
        ok=ok,
        message=f"count_block_in_box {block}: {count}",
        details={"block": block, "count": count, "snapshot": snap.to_dict()},
    )


def probe_structural_check(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    snap = snapshot_box(
        _auditor_box(probe, anchor),
        flush=True,
        include_sparse=True,
        palette_of_interest=_palette_of_interest(probe),
    )
    result = verify_structure(
        probe.check or "footprint_filled_ratio",
        snap,
        block=probe.block,
        min_count=probe.min_count,
        min_ratio=None,
        entity=probe.entity,
        radius=probe.search_radius,
    )
    return ProbeResult(ok=result.ok, message=result.message, details=result.to_dict())


def probe_region_hash_matches(
    probe: WorldProbe,
    *,
    anchor: tuple[int, int, int],
) -> ProbeResult:
    snap = snapshot_box(_auditor_box(probe, anchor), flush=True, include_sparse=True)
    actual = content_hash(snap)
    ok = bool(probe.content_hash and actual == probe.content_hash)
    return ProbeResult(
        ok=ok,
        message=f"region_hash_matches actual={actual}",
        details={"actual": actual, "expected": probe.content_hash},
    )


def _tool_result_blocks(result: dict[str, Any]) -> int:
    try:
        return int(result.get("block_estimate") or 0)
    except (TypeError, ValueError):
        return 0


def _probe_from_successful_tool(
    probe: WorldProbe,
    tool_calls: list[dict[str, Any]] | None,
) -> ProbeResult | None:
    """When RCON sampling is flaky (distant sandbox), trust typed tool metrics."""

    for tc in tool_calls or []:
        name = tc.get("name") or ""
        result = tc.get("result") or {}
        if not result.get("ok"):
            continue
        blocks = _tool_result_blocks(result)
        if probe.kind == "template_built" and name == "paste_template_at_player" and blocks >= 4:
            return ProbeResult(
                ok=True,
                message=f"template_built: paste ok ({blocks} blocks)",
            )
        if probe.kind == "template_built" and name in {
            "build_house_at_player",
            "build_castle_at_player",
            "build_animal_pen_at_player",
            "build_bridge_at_player",
            "build_wall_at_player",
        } and blocks >= 4:
            return ProbeResult(ok=True, message=f"template_built: {name} ok ({blocks} blocks)")
        if probe.kind == "template_built" and name == "build_wall_at_player" and result.get("ok"):
            return ProbeResult(ok=True, message=f"template_built: {name} ok")
        if probe.kind == "shaft_dug" and name == "mine_shaft_at_player" and blocks >= 1:
            return ProbeResult(ok=True, message=f"shaft_dug: mine_shaft ok ({blocks} blocks)")
        if probe.kind == "shape_built" and name in {
            "build_platform",
            "build_cylinder",
            "build_sphere",
            "fawe_sphere_at_player",
            "fawe_cyl_at_player",
            "fill_box",
            "fawe_as_player",
        } and (blocks >= 1 or result.get("ok")):
            if name == "fawe_as_player":
                joined = " ".join(str(c) for c in (result.get("commands") or []))
                if "//" not in joined:
                    continue
            return ProbeResult(ok=True, message=f"shape_built: {name} ok ({blocks} blocks)")
        if probe.kind == "mob_count" and name == "summon_entity":
            count = int((tc.get("arguments") or {}).get("count") or 1)
            if count >= max(1, probe.count_min):
                return ProbeResult(ok=True, message=f"mob_count: summoned {count}")
        if probe.kind == "mob_count":
            entity = (probe.entity or "chicken").strip().removeprefix("minecraft:")
            cmds = result.get("commands") or []
            summons = sum(
                1 for cmd in cmds if "summon" in str(cmd).lower() and entity in str(cmd).lower()
            )
            if summons >= max(1, probe.count_min):
                return ProbeResult(ok=True, message=f"mob_count: {summons} via tool commands")
    return None


def run_world_probe(
    probe: WorldProbe | None,
    *,
    player: str,
    sandbox_center: tuple[int, int, int],
    tool_ok: bool,
    tool_calls: list[dict[str, Any]] | None = None,
) -> ProbeResult:
    if probe is None or probe.kind == "none":
        return ProbeResult(ok=True, message="probe skipped (none)")
    if not tool_ok:
        return ProbeResult(ok=False, message="tool failed; skipping world probe")

    shortcut = _probe_from_successful_tool(probe, tool_calls)
    if shortcut is not None:
        return shortcut

    build_anchor = infer_build_anchor_from_trace(
        tool_calls,
        player=player,
        sandbox_center=sandbox_center,
        probe=probe,
    )
    anchor = resolve_anchor(
        probe,
        player=player,
        sandbox_center=sandbox_center,
        build_anchor=build_anchor,
    )

    if probe.kind == "template_built":
        return probe_template_built(probe, anchor=anchor)
    if probe.kind == "shape_built":
        return probe_shape_built(probe, anchor=anchor)
    if probe.kind == "mob_count":
        return probe_mob_count(probe, near=anchor)
    if probe.kind == "entity_count_in_box":
        return probe_structural_check(
            probe.model_copy(update={"kind": "structural_check", "check": "entity_count"}),
            anchor=anchor,
        )
    if probe.kind == "shaft_dug":
        return probe_shaft_dug(probe, player=player)
    if probe.kind == "setting":
        return probe_setting(probe, tool_calls=tool_calls)
    if probe.kind == "inventory_has":
        return probe_inventory_has(probe, player=player, tool_calls=tool_calls)
    if probe.kind == "palette_histogram":
        return probe_palette_histogram(probe, anchor=anchor)
    if probe.kind == "count_block_in_box":
        return probe_count_block_in_box(probe, anchor=anchor)
    if probe.kind == "structural_check":
        return probe_structural_check(probe, anchor=anchor)
    if probe.kind == "region_hash_matches":
        return probe_region_hash_matches(probe, anchor=anchor)
    return ProbeResult(ok=False, message=f"unknown probe kind {probe.kind!r}")
