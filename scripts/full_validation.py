"""End-to-end validation: paste every catalog template (+ optional mobs).

Uses console ``agent-paste-at`` (native FAWE at fixed coords). **Never teleports
or requires an online player** for the QA campus populate.

Layout (dedicated remote pad, far from spawn / normal play):

    Templates: footprint-aware shelf packing at (20000, 120, 20000).
               Each cell reserves schem width×depth + aisle; next cell starts
               after prior extents (row wrap by max depth in shelf). Condensed
               but no overlap — mega builds get exclusive rects.
               Oak signs label each stand; ``docs/QA_GRID.md`` maps cells.
    Mob pen:   centered around (20000, 120, 21500) (skipped with --skip-mobs).

Operator QA workflow::

    make qa-grid          # paste all templates, write docs/QA_GRID.md
    make full-validation  # same + summon supported mobs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from agent.templates import catalog as template_catalog
from agent.tools import _rcon, summon_entity

REPO_ROOT = Path(__file__).resolve().parents[1]
QA_GRID_PATH = REPO_ROOT / "docs" / "QA_GRID.md"
STATUS_PATH = "/data/plugins/NeighborhoodAgent/qa_last_paste.json"
MC_CONTAINER = os.environ.get("MC_CONTAINER", "mc-lan")
QA_WORLD = os.environ.get("AGENT_QA_WORLD", "world")

# Elevated artificial pad — above typical mountain peaks so terrain cannot cut
# through the campus. Cells sized from catalog footprint (not fixed stride).
GRID_ORIGIN = (20000, 120, 20000)
# Adjacent strip for curated refill QA — south of main campus, no wipe of keepers.
# Must stay past campus max_z (gold shelf pack ends ~21199); pad carve uses bz1-16.
REFILL_ORIGIN = (20000, 120, 21220)
REFILL_ROW_BASE = 100  # table rows 100+ so merge doesn't collide with campus 0..N
# Shelf packing: wrap when adding the next cell would exceed this row budget
# (single mega cells may be wider and still sit alone on their shelf).
ROW_BUDGET = 400
CELL_AISLE = 4
CELL_BACK = 2  # stand/sign cushion on the north edge of each reserved rect
PLAYER_MARGIN = 2  # mirrors SchematicPlacement.PLAYER_MARGIN
MIN_CELL_W = 12
MIN_CELL_D = 16
# Wide apron so BlueMap doesn't show mountain shoulders "clipping" the pad.
PAD_BORDER = 72
# Carve from below the floating pad up through overview air so peaks cannot
# remain inside or beside the campus footprint.
PAD_CLEAR_BOTTOM = 64
PAD_CLEAR_TOP_MIN = 240
PAD_STONE_THICKNESS = 8
# Paper forceload add rejects >256 chunks; tile below that.
FORCELOAD_TILE_BLOCKS = 14 * 16  # 224 blocks → 14×14 = 196 chunks
# Prior campuses (void on re-run so leftover pads don't confuse overview).
_LEGACY_ORIGINS = (
    (13000, 96, 13000),
)
# Materials that count as paste content on the grass skin (y-1 stubs).
# Do NOT count grass_block — that is the pad itself (previous false 101/101).
_STUB_MATS = (
    "stone",
    "dirt",
    "farmland",
    "water",
    "sugar_cane",
    "oak_log",
    "dark_oak_log",
    "spruce_log",
    "birch_log",
    "jungle_log",
    "oak_leaves",
    "dark_oak_leaves",
    "spruce_leaves",
    "oak_sapling",
    "spruce_sapling",
    "dark_oak_sapling",
    "oak_fence",
    "oak_planks",
    "spruce_planks",
    "cobblestone",
    "stone_bricks",
    "glass",
    "lantern",
    "torch",
    "hay_block",
    "white_wool",
    "smooth_stone",
    "bricks",
    "podzol",
    "coarse_dirt",
    "moss_block",
    "crafting_table",
    "chest",
)

PEN_CENTER = (20000, 120, 21500)
PEN_RADIUS = 60


def _gold_ids() -> set[str]:
    raw = template_catalog.load_catalog()
    return {
        str(item.get("id"))
        for item in (raw.get("templates") or [])
        if item.get("gold")
    }


def _rcon_retry(command: str, *, timeout: float = 60, attempts: int = 5) -> str:
    """RCON with backoff — large fills can briefly reset the connection."""

    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            return _rcon(command, timeout=timeout) or ""
        except Exception as exc:  # noqa: BLE001 — transient docker/rcon blips
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"rcon failed after {attempts} attempts: {last_err}")


def _fill_chunked(
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    block: str,
    *,
    chunk_x: int = 96,
    chunk_y: int = 48,
    chunk_z: int = 96,
) -> None:
    """Run vanilla /fill over a large cuboid without hitting command limits.

    Prefers large tiles when ``max_block_modifications`` is raised (see main).
    """

    xa, xb = sorted((x1, x2))
    ya, yb = sorted((y1, y2))
    za, zb = sorted((z1, z2))
    n = 0
    for x in range(xa, xb + 1, chunk_x):
        ex = min(x + chunk_x - 1, xb)
        for y in range(ya, yb + 1, chunk_y):
            ey = min(y + chunk_y - 1, yb)
            for z in range(za, zb + 1, chunk_z):
                ez = min(z + chunk_z - 1, zb)
                _rcon_retry(f"fill {x} {y} {z} {ex} {ey} {ez} {block}", timeout=120)
                n += 1
                if n % 40 == 0:
                    print(f"    fill progress {n} tiles ({block})…", flush=True)


def _forceload_area(x1: int, z1: int, x2: int, z2: int) -> None:
    """Force-load a region in ≤256-chunk tiles (Paper hard limit)."""

    xa, xb = sorted((x1, x2))
    za, zb = sorted((z1, z2))
    tile = FORCELOAD_TILE_BLOCKS
    for x in range(xa, xb + 1, tile):
        ex = min(x + tile - 1, xb)
        for z in range(za, zb + 1, tile):
            ez = min(z + tile - 1, zb)
            out = _rcon(f"forceload add {x} {z} {ex} {ez}", timeout=60) or ""
            if "Too many chunks" in out:
                # Fallback: single-chunk marks for this tile.
                for cx in range(x // 16 * 16, ex + 1, 16):
                    for cz in range(z // 16 * 16, ez + 1, 16):
                        _rcon(f"forceload add {cx} {cz} {cx} {cz}", timeout=30)


def _prepare_flat_area(
    x1: int,
    z1: int,
    x2: int,
    z2: int,
    *,
    surface_y: int,
    clear_height: int | None = None,
) -> None:
    """Carve a thick artificial pad and void terrain through a tall column.

    Clears from PAD_CLEAR_BOTTOM (or stone floor) up through clear top so
    mountain shoulders beside/through the campus cannot remain in BlueMap.
    """

    top = (
        PAD_CLEAR_TOP_MIN
        if clear_height is None
        else surface_y + clear_height
    )
    stone_bottom = surface_y - PAD_STONE_THICKNESS
    void_bottom = min(PAD_CLEAR_BOTTOM, stone_bottom)
    _forceload_area(x1, z1, x2, z2)
    # Void the full vertical column (terrain below + old builds + peaks).
    _fill_chunked(x1, void_bottom, z1, x2, top, z2, "air")
    _fill_chunked(x1, stone_bottom, z1, x2, surface_y - 1, z2, "stone")
    _fill_chunked(x1, surface_y - 1, z1, x2, surface_y - 1, z2, "grass_block")


def _clone_air_count(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> int | None:
    """Return air-block count from clone filtered air, or None on failure."""

    staging_y = min(320, PAD_CLEAR_TOP_MIN + 40)
    out = (
        _rcon(
            f"clone {x1} {y1} {z1} {x2} {y2} {z2} "
            f"{x1} {staging_y} {z1} filtered air force",
            timeout=60,
        )
        or ""
    )
    match = re.search(r"cloned (\d+)", out)
    if match:
        return int(match.group(1))
    if "No blocks" in out or "no blocks" in out.lower():
        return 0
    return None


def _count_non_air(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> int:
    """Count non-air blocks via clone filtered air (volume − air)."""

    xa, xb = sorted((x1, x2))
    ya, yb = sorted((y1, y2))
    za, zb = sorted((z1, z2))
    volume = (xb - xa + 1) * (yb - ya + 1) * (zb - za + 1)
    if volume <= 32000:
        air = _clone_air_count(xa, ya, za, xb, yb, zb)
        if air is not None:
            return max(0, volume - air)
    # Keep each clone under Paper's 32768 block modification cap.
    chunk_x, chunk_y, chunk_z = 16, 16, 16
    total_air = 0
    counted = 0
    for x in range(xa, xb + 1, chunk_x):
        ex = min(x + chunk_x - 1, xb)
        for y in range(ya, yb + 1, chunk_y):
            ey = min(y + chunk_y - 1, yb)
            for z in range(za, zb + 1, chunk_z):
                ez = min(z + chunk_z - 1, zb)
                vol = (ex - x + 1) * (ey - y + 1) * (ez - z + 1)
                counted += vol
                air = _clone_air_count(x, y, z, ex, ey, ez)
                if air is None:
                    # Unloaded / failed slice — no non-air credit.
                    total_air += vol
                else:
                    total_air += air
    return max(0, counted - total_air)


def _min_non_air_for(meta) -> int:
    """Minimum footprint solids before a paste counts as world-verified.

    Uses schematic footprint (not catalog max_blocks — often a loose 500 cap
    that would reject tiny props like lamp posts / flag poles).
    """

    fw, fh, fd = meta.footprint
    volume = max(1, fw * max(fh, 1) * fd)
    if volume <= 48 or fh <= 1:
        return 2
    return max(3, min(30, volume // 40))


def _count_stub_layer(x1: int, z1: int, x2: int, z2: int, y: int) -> int:
    """Count non-grass solids on the grass skin (y-1).

    Uses block probes (fill-replace counts are unreliable on this Paper build).
    Grass pad blocks are ignored so the empty platform cannot fake a paste.
    """

    total = 0
    step = 1 if (x2 - x1) <= 12 and (z2 - z1) <= 12 else 2
    for x in range(x1, x2 + 1, step):
        for z in range(z1, z2 + 1, step):
            grass = _rcon(f"execute if block {x} {y} {z} minecraft:grass_block", timeout=10) or ""
            if "Test failed" not in grass:
                continue
            solid = _rcon(f"execute unless block {x} {y} {z} minecraft:air", timeout=10) or ""
            if "Test failed" not in solid:
                total += 1
    return total


def _world_paste_solids(
    stand_x: int,
    stand_y: int,
    stand_z: int,
    *,
    fw: int,
    fh: int,
    fd: int,
) -> int:
    """Count non-air above the pad (stand Y). Fast path — no per-block stub probes."""

    half_w = max(fw // 2 + 4, 8)
    depth = max(fd + 12, 16)
    height = max(min(fh + 4, 64), 8)
    x1, x2 = stand_x - half_w, stand_x + half_w
    z1, z2 = stand_z + 1, stand_z + depth
    _forceload_area(x1, z1, x2, z2)
    return _count_non_air(x1, stand_y, z1, x2, stand_y + height - 1, z2)


def cell_reserved_size(fw: int, fd: int) -> tuple[int, int]:
    """Exclusive reserved width×depth for a facing-south paste from the stand.

    Facing offset places the build south of the stand; near edge ≈ clearance
    (fd/2 + margin), span = fd. Verification probes use fd+12. Take the max
    plus aisle/back so neighbor prepares never clip a mega paste.
    """

    cell_w = max(int(fw), MIN_CELL_W) + 2 * CELL_AISLE
    facing_extent = (int(fd) // 2) + PLAYER_MARGIN + int(fd)
    verify_extent = int(fd) + 12
    cell_d = max(facing_extent, verify_extent, MIN_CELL_D) + CELL_AISLE + CELL_BACK
    return cell_w, cell_d


@dataclass(frozen=True)
class PackedCell:
    template_id: str
    row: int
    col: int
    stand_x: int
    stand_y: int
    stand_z: int
    min_x: int
    max_x: int
    min_z: int
    max_z: int
    reserved_w: int
    reserved_d: int
    fw: int
    fh: int
    fd: int


def pack_campus(
    metas: list,
    *,
    origin: tuple[int, int, int] = GRID_ORIGIN,
    row_base: int = 0,
) -> list[PackedCell]:
    """Shelf-pack templates: left-to-right, wrap by max depth in the current row.

    Catalog order preserved. Each reserved rect is exclusive (no overlap).
    ``row_base`` offsets row indices (refill strip uses 100+).
    """

    ox, oy, oz = origin
    cursor_x, cursor_z = ox, oz
    row_depth = 0
    row = 0
    col = 0
    out: list[PackedCell] = []
    for meta in metas:
        fw, fh, fd = meta.footprint
        cell_w, cell_d = cell_reserved_size(fw, fd)
        if cursor_x > ox and (cursor_x - ox) + cell_w > max(ROW_BUDGET, cell_w):
            cursor_x = ox
            cursor_z += row_depth
            row_depth = 0
            row += 1
            col = 0
        stand_x = cursor_x + cell_w // 2
        stand_z = cursor_z + CELL_BACK
        out.append(
            PackedCell(
                template_id=meta.id,
                row=row_base + row,
                col=col,
                stand_x=stand_x,
                stand_y=oy,
                stand_z=stand_z,
                min_x=cursor_x,
                max_x=cursor_x + cell_w - 1,
                min_z=cursor_z,
                max_z=cursor_z + cell_d - 1,
                reserved_w=cell_w,
                reserved_d=cell_d,
                fw=int(fw),
                fh=int(fh),
                fd=int(fd),
            )
        )
        cursor_x += cell_w
        row_depth = max(row_depth, cell_d)
        col += 1
    return out


def merge_qa_cells(
    prior: list[CellResult],
    new_cells: list[CellResult],
) -> list[CellResult]:
    """Replace prior cells with the same template_id; append new ids."""

    by_id = {c.template_id: c for c in prior}
    for cell in new_cells:
        by_id[cell.template_id] = cell
    # Stable: prior order, then any brand-new ids in new_cells order.
    seen: set[str] = set()
    out: list[CellResult] = []
    for c in prior:
        merged = by_id[c.template_id]
        out.append(merged)
        seen.add(c.template_id)
    for c in new_cells:
        if c.template_id not in seen:
            out.append(c)
            seen.add(c.template_id)
    return out


def campus_bounds(packed: list[PackedCell]) -> tuple[int, int, int, int]:
    """Inclusive world AABB of reserved rects (x1,z1,x2,z2)."""

    if not packed:
        ox, _, oz = GRID_ORIGIN
        return ox, oz, ox, oz
    return (
        min(p.min_x for p in packed),
        min(p.min_z for p in packed),
        max(p.max_x for p in packed),
        max(p.max_z for p in packed),
    )


def _pad_clear_top(max_fh: int, surface_y: int) -> int:
    return max(PAD_CLEAR_TOP_MIN, surface_y + max(max_fh, 1) + 24)


def _void_legacy_campuses(*, span_x: int, span_z: int) -> None:
    """Air out prior QA pads so they don't look like the active campus."""

    for ox, oy, oz in _LEGACY_ORIGINS:
        if (ox, oy, oz) == GRID_ORIGIN:
            continue
        print(f"  voiding legacy campus at ({ox},{oy},{oz})")
        _forceload_area(ox - 32, oz - 32, ox + span_x, oz + span_z)
        _fill_chunked(
            ox - 32,
            oy - 6,
            oz - 32,
            ox + span_x,
            oy + 80,
            oz + span_z,
            "air",
        )


def _sign_line(text: str, max_len: int = 15) -> str:
    """Plain SNBT string for Paper 26+ sign messages (not JSON component blobs).

    Modern Minecraft stores sign lines as NBT text components. A quoted JSON
    string like '{"text":"Hi"}' is displayed literally; pass plain text instead.
    """
    cleaned = re.sub(r"[^\w \-./★]", "", text)[:max_len]
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _place_label(x: int, y: int, z: int, template_id: str, title: str, gold: bool) -> None:
    """Oak sign one block north of the stand: title / id / ★ gold / (blank)."""
    sx, sy, sz = x, y, z - 1
    line1 = _sign_line(title)
    line2 = _sign_line(template_id)
    line3 = _sign_line("★ gold" if gold else "")
    line4 = _sign_line("")
    cmd = (
        f"setblock {sx} {sy} {sz} oak_sign[rotation=8]"
        f"{{front_text:{{messages:[{line1},{line2},{line3},{line4}]}},is_waxed:1b}}"
    )
    _rcon(cmd, timeout=15)


def resign_all_signs(cells: list[CellResult]) -> int:
    """Replace QA campus signs from sidecar coords — no paste, no player TP."""
    ok = 0
    for cell in cells:
        try:
            _place_label(
                cell.stand_x,
                cell.stand_y,
                cell.stand_z,
                cell.template_id,
                cell.title,
                cell.gold,
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001 — labels are best-effort
            print(f"  [sign warn] {cell.template_id}: {exc}")
    return ok


def _read_paste_status() -> dict:
    try:
        raw = subprocess.check_output(
            ["docker", "exec", MC_CONTAINER, "cat", STATUS_PATH],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return {}


def _agent_paste_at(
    stand_x: int,
    stand_y: int,
    stand_z: int,
    template_id: str,
    *,
    world: str = QA_WORLD,
    timeout_sec: float = 60.0,
) -> dict:
    """Force-paste via console agent-paste-at (no player, no teleport)."""

    before = _read_paste_status()
    before_seq = int(before.get("seq") or 0)
    out = (
        _rcon(
            f"agent-paste-at {world} {stand_x} {stand_y} {stand_z} {template_id}",
            timeout=30,
        )
        or ""
    )
    if "Unknown or incomplete command" in out or "I'm not sure" in out:
        return {
            "ok": False,
            "verified": False,
            "message": (
                "agent-paste-at missing — rebuild/deploy NeighborhoodAgent "
                f"({out.strip()[:120]})"
            ),
        }
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        status = _read_paste_status()
        seq = int(status.get("seq") or 0)
        if (
            seq > before_seq
            and status.get("template_id") == template_id
            and status.get("done")
        ):
            return status
        time.sleep(0.15)
    return {
        "ok": False,
        "verified": False,
        "message": f"timed out waiting for agent-paste-at {template_id}",
    }


@dataclass
class CellResult:
    template_id: str
    title: str
    gold: bool
    row: int
    col: int
    stand_x: int
    stand_y: int
    stand_z: int
    ok: bool
    verified: bool
    used_schematic: bool
    summary: str
    error: str = ""
    non_air: int = 0
    plugin_verified: bool = False
    min_x: int = 0
    max_x: int = 0
    min_z: int = 0
    max_z: int = 0
    reserved_w: int = 0
    reserved_d: int = 0
    fw: int = 0
    fh: int = 0
    fd: int = 0


def _paste_timeout(fw: int, fh: int, fd: int) -> float:
    volume = max(1, fw * max(fh, 1) * fd)
    if volume >= 500_000:
        return 180.0
    if volume >= 80_000:
        return 120.0
    return 60.0


def _paste_one(
    meta,
    *,
    packed: PackedCell,
    is_gold: bool,
) -> CellResult:
    """Console paste at fixed stand — no player, no teleport, no per-cell TP clear."""

    fw, fh, fd = packed.fw, packed.fh, packed.fd
    x, y, z = packed.stand_x, packed.stand_y, packed.stand_z
    # Light forceload of reserved rect; campus pad already carved. Site clear
    # happens inside native FAWE clearPad (from floor Y up only).
    _forceload_area(packed.min_x, packed.min_z, packed.max_x, packed.max_z)
    try:
        _place_label(x, y, z, meta.id, meta.title, is_gold)
    except Exception as exc:  # noqa: BLE001 — labels are best-effort
        print(f"  [sign warn] {meta.id}: {exc}")
    timeout = _paste_timeout(fw, fh, fd)
    status = _agent_paste_at(x, y, z, meta.id, timeout_sec=timeout)
    if not status.get("ok"):
        status = _agent_paste_at(x, y, z, meta.id, timeout_sec=timeout)
    plugin_ok = bool(status.get("ok"))
    plugin_verified = bool(status.get("verified"))
    message = str(status.get("message") or "")
    non_air = 0
    # Always world-count above the pad — never fake non_air=1 from plugin verify.
    if plugin_ok:
        non_air = _world_paste_solids(x, y, z, fw=fw, fh=fh, fd=fd)
        min_solid = _min_non_air_for(meta)
        world_ok = non_air >= min_solid
    else:
        world_ok = False
        min_solid = _min_non_air_for(meta)
    ok = plugin_ok and world_ok
    verified = plugin_verified and world_ok
    if plugin_ok and not world_ok:
        message = (
            f"paste reported ok but footprint non_air={non_air} "
            f"< min={min_solid}"
        )
    kill_r = 24 if max(fw, fd) < 40 else min(80, max(fw, fd) // 2 + 16)
    _rcon(
        f"kill @e[type=!player,x={x},y={y},z={z},distance=..{kill_r}]",
        timeout=15,
    )
    return CellResult(
        template_id=meta.id,
        title=meta.title,
        gold=is_gold,
        row=packed.row,
        col=packed.col,
        stand_x=x,
        stand_y=y,
        stand_z=z,
        ok=ok,
        verified=verified,
        used_schematic=plugin_ok,
        summary=message[:120],
        error=message[:200] if not ok else "",
        non_air=non_air,
        plugin_verified=plugin_verified,
        min_x=packed.min_x,
        max_x=packed.max_x,
        min_z=packed.min_z,
        max_z=packed.max_z,
        reserved_w=packed.reserved_w,
        reserved_d=packed.reserved_d,
        fw=fw,
        fh=fh,
        fd=fd,
    )


def paste_all(packed: list[PackedCell]) -> list[CellResult]:
    template_catalog.reload_catalog()
    by_id = {m.id: m for m in template_catalog.iter_templates()}
    gold = _gold_ids()
    results: list[CellResult] = []
    for slot in packed:
        meta = by_id.get(slot.template_id)
        if meta is None:
            continue
        is_gold = meta.id in gold
        cell = _paste_one(meta, packed=slot, is_gold=is_gold)
        results.append(cell)
        flag = "OK" if cell.ok else "X "
        vflag = "V" if cell.verified else " "
        gflag = "G" if is_gold else " "
        print(
            f"  [{flag}|{vflag}|{gflag}] r{slot.row:02d}c{slot.col:02d} "
            f"{meta.id:30s} ({slot.stand_x},{slot.stand_y},{slot.stand_z}) "
            f"res={slot.reserved_w}x{slot.reserved_d} non_air={cell.non_air} "
            f"{cell.summary[:45]}",
            flush=True,
        )
    return results


def retry_failed(prior: list[CellResult]) -> list[CellResult]:
    """Re-attempt only failed cells; keep successful pastes in place."""

    template_catalog.reload_catalog()
    by_id = {m.id: m for m in template_catalog.iter_templates()}
    gold = _gold_ids()
    out: list[CellResult] = []
    for cell in prior:
        if cell.ok:
            out.append(cell)
            continue
        meta = by_id.get(cell.template_id)
        if meta is None:
            out.append(cell)
            continue
        fw, fh, fd = meta.footprint
        cell_w, cell_d = cell_reserved_size(fw, fd)
        packed = PackedCell(
            template_id=meta.id,
            row=cell.row,
            col=cell.col,
            stand_x=cell.stand_x,
            stand_y=cell.stand_y,
            stand_z=cell.stand_z,
            min_x=cell.min_x or (cell.stand_x - cell_w // 2),
            max_x=cell.max_x or (cell.stand_x - cell_w // 2 + cell_w - 1),
            min_z=cell.min_z or (cell.stand_z - CELL_BACK),
            max_z=cell.max_z or (cell.stand_z - CELL_BACK + cell_d - 1),
            reserved_w=cell.reserved_w or cell_w,
            reserved_d=cell.reserved_d or cell_d,
            fw=int(fw),
            fh=int(fh),
            fd=int(fd),
        )
        print(f"  [retry] {meta.id} @ ({cell.stand_x},{cell.stand_y},{cell.stand_z})")
        new_cell = _paste_one(meta, packed=packed, is_gold=meta.id in gold)
        flag = "OK" if new_cell.ok else "X "
        print(f"  [{flag}] {meta.id}: {new_cell.summary[:80]}")
        out.append(new_cell)
    return out


def write_qa_grid(results: list[CellResult], *, player: str) -> Path:
    ox, oy, oz = GRID_ORIGIN
    ok = sum(1 for r in results if r.ok)
    verified = sum(1 for r in results if r.verified)
    gold_n = sum(1 for r in results if r.gold)
    rows = max((r.row for r in results), default=-1) + 1
    x1, z1, x2, z2 = campus_bounds(
        [
            PackedCell(
                template_id=r.template_id,
                row=r.row,
                col=r.col,
                stand_x=r.stand_x,
                stand_y=r.stand_y,
                stand_z=r.stand_z,
                min_x=r.min_x,
                max_x=r.max_x,
                min_z=r.min_z,
                max_z=r.max_z,
                reserved_w=r.reserved_w,
                reserved_d=r.reserved_d,
                fw=r.fw,
                fh=r.fh,
                fd=r.fd,
            )
            for r in results
            if r.reserved_w > 0
        ]
    )
    span_x = max(0, x2 - x1 + 1)
    span_z = max(0, z2 - z1 + 1)
    mid_x = (x1 + x2) // 2
    mid_z = (z1 + z2) // 2
    max_fh = max((r.fh for r in results if r.fh), default=48)
    clear_top = _pad_clear_top(max_fh, oy)
    first = next((r for r in results if r.row == 0 and r.col == 0), results[0] if results else None)
    first_stand = (
        f"{first.stand_x} {first.stand_y} {first.stand_z}"
        if first
        else f"{ox} {oy} {oz}"
    )
    lines = [
        "# Template QA grid",
        "",
        "Remote paste pad for keep/demote review. Far from spawn; does not wipe the world.",
        "",
        "## How to view",
        "",
        f"- First cell stand: `{first_stand}`",
        f"- Footprint-aware shelf packing: **{rows}** shelves, row budget "
        f"**{ROW_BUDGET}**, aisle **{CELL_AISLE}** "
        f"(span ~{span_x}×{span_z}; bounds `{x1},{z1}`..`{x2},{z2}`)",
        f"- Each cell reserves schem width×depth + margin; next cell starts "
        f"after prior extents (wrap by max depth in the shelf). No overlap.",
        f"- Artificial pad at Y={oy} (stone/{PAD_STONE_THICKNESS} + grass; "
        f"void Y={PAD_CLEAR_BOTTOM}..{clear_top}, border {PAD_BORDER})",
        f"- Pasted: **{ok}/{len(results)}** ok · **{verified}** world-verified · "
        f"**{gold_n}** gold",
        f"- Populate mode: **console `agent-paste-at`** (no player; "
        f"does **not** teleport anyone). Operator label: `{player}`",
        "",
        "**Populate never moves players.** `make qa-grid` pastes via console FAWE "
        "at fixed stand coords. You can keep playing at spawn while it runs.",
        "",
        "World verification counts non-air **above** the grass pad. "
        "Grass pad blocks alone do not count.",
        "",
        "### Teleport (viewing only — optional)",
        "",
        "Air overview (one glance):",
        "",
        "```",
        f"/tp @s {mid_x} {oy + 84} {mid_z}",
        "```",
        "",
        "Ground / first cell:",
        "",
        "```",
        f"/tp @s {first_stand}",
        "```",
        "",
        "From host:",
        "",
        "```bash",
        f'./mc.sh cmd "tp <your-name> {mid_x} {oy + 84} {mid_z}"',
        "```",
        "",
        "BlueMap: open the map near those coords, then **Update Map** / refresh "
        "tiles if the pad still looks like the old mountain cut.",
        "",
        "Each stand has an oak sign: **title** / **template id** / "
        "**★ gold** (or blank) — plain text, not JSON.",
        "",
        "Re-label without re-paste: `make qa-resign-signs`.",
        "",
        "## Mark fails (in-game demote)",
        "",
        "**Any op** (`neighborhood.agent.qa`, default: op) — split review across ops.",
        "Each demote/promote logs `player` in `qa-demotions.jsonl`.",
        "",
        "1. Get a hoe: `/qa-hoe` (or `/agent qa-hoe`).",
        "2. **Left-click** any block on a paste → chat confirms "
        "`Demoted <id> (was gold)` or `Already demoted`.",
        "3. **Right-click** with the same hoe to **re-promote** / undo demote.",
        "4. Demotions append to "
        "`data/plugins/NeighborhoodAgent/qa-demotions.jsonl` (survives restart).",
        "5. Apply to catalog: `make qa-apply-demotions` "
        "(sets `gold: false`, restarts `mc-agent`).",
        "",
        "Give the hoe (any op name — only when reviewing):",
        "",
        "```",
        "/qa-hoe",
        "/give <op-name> wooden_hoe 1",
        "```",
        "",
        'Or from host: `./mc.sh cmd "give <op-name> wooden_hoe 1"`.',
        "",
        "Live agent tests (`agent-as`, scripted TP) stay firecrab93-only — "
        "human QA demote is any op.",
        "",
        "Do **not** mass-scrape replacements until QA identifies junk.",
        "",
        "## Cell map",
        "",
        "| row | col | gold | template_id | title | stand (x y z) | reserved | non_air | paste |",
        "| ---:| ---:| :---:| --- | --- | --- | --- | ---:| --- |",
    ]
    for r in results:
        g = "★" if r.gold else ""
        if r.ok and r.verified:
            status = "ok"
        elif r.ok:
            status = "unverified"
        else:
            status = "FAIL"
        reserved = f"{r.reserved_w}×{r.reserved_d}" if r.reserved_w else "?"
        lines.append(
            f"| {r.row} | {r.col} | {g} | `{r.template_id}` | {r.title} | "
            f"`{r.stand_x} {r.stand_y} {r.stand_z}` | {reserved} | "
            f"{r.non_air} | {status} |"
        )
    fails = [r for r in results if not r.ok]
    if fails:
        lines.extend(["", "## Failures", ""])
        for r in fails:
            lines.append(f"- `{r.template_id}` @ ({r.stand_x},{r.stand_y},{r.stand_z}): {r.error}")
    lines.append("")
    QA_GRID_PATH.parent.mkdir(parents=True, exist_ok=True)
    QA_GRID_PATH.write_text("\n".join(lines), encoding="utf-8")
    sidecar = QA_GRID_PATH.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "origin": list(GRID_ORIGIN),
                "layout": "shelf",
                "row_budget": ROW_BUDGET,
                "aisle": CELL_AISLE,
                "span": [span_x, span_z],
                "bounds": [x1, z1, x2, z2],
                "player": player,
                "cells": [asdict(r) for r in results],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return QA_GRID_PATH


_MOB_LIST = [
    "chicken", "pig", "cow", "sheep", "horse", "donkey", "mule",
    "goat", "rabbit", "bee", "llama", "trader_llama", "cat", "wolf",
    "fox", "frog", "turtle", "axolotl", "panda", "polar_bear",
    "parrot", "ocelot", "villager", "wandering_trader", "iron_golem",
    "snow_golem", "armor_stand", "zombie", "skeleton", "creeper",
    "spider", "enderman", "slime", "blaze", "ghast", "phantom",
    "drowned", "husk", "stray", "witch", "pillager", "vex",
    "evoker", "ravager", "vindicator", "guardian", "squid", "salmon",
    "cod", "pufferfish", "tropical_fish", "dolphin", "glow_squid",
    "bat", "allay", "camel", "sniffer", "armadillo", "happy_ghast",
]


def _spawn_supported_mobs() -> tuple[list[str], list[tuple[str, str]]]:
    cx, cy, cz = PEN_CENTER
    grid_w = 8
    summoned: list[str] = []
    failed: list[tuple[str, str]] = []
    for idx, mob in enumerate(_MOB_LIST):
        col = idx % grid_w
        row = idx // grid_w
        x = cx + (col - grid_w // 2) * 4
        z = cz + (row - grid_w // 2) * 4
        r = summon_entity(mob, x, cy, z, count=1)
        if r.ok:
            summoned.append(mob)
            print(f"  [OK]  spawn {mob:18s} at ({x},{cy},{z})")
        else:
            err = (r.error or "").splitlines()[0]
            failed.append((mob, err[:140]))
            print(f"  [X ]  spawn {mob:18s} -> {err[:80]}")
    return summoned, failed


def _load_prior_cells() -> list[CellResult]:
    sidecar = QA_GRID_PATH.with_suffix(".json")
    if not sidecar.is_file():
        raise SystemExit(f"missing {sidecar}; run a full qa-grid first")
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    cells: list[CellResult] = []
    for cell in raw.get("cells") or []:
        # Ignore unknown keys from older sidecars / forward-compat fields.
        known = {f.name for f in fields(CellResult)}
        cells.append(CellResult(**{k: v for k, v in cell.items() if k in known}))
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-mobs",
        action="store_true",
        help="Paste templates only (QA grid). Also set by AGENT_VALIDATION_SKIP_MOBS=1.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Only re-paste cells marked FAIL in docs/QA_GRID.json (keep successes).",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Skip pad carve (pad already flattened). Paste only.",
    )
    parser.add_argument(
        "--resign-signs",
        action="store_true",
        help="Only replace oak signs from docs/QA_GRID.json (no paste, no TP).",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated template ids to paste (selective). Implies no full wipe.",
    )
    parser.add_argument(
        "--refill-strip",
        action="store_true",
        help=(
            "Paste --only ids onto the adjacent refill QA strip at "
            f"{REFILL_ORIGIN} (does not wipe the known-good campus). "
            "Merges cells into docs/QA_GRID.json."
        ),
    )
    parser.add_argument(
        "--gold-only",
        action="store_true",
        help=(
            "Paste only catalog gold:true templates. Full campus wipe "
            "(covers prior QA_GRID bounds + new pack); replaces the index "
            "(does not merge non-gold keepers)."
        ),
    )
    args = parser.parse_args()
    skip_mobs = args.skip_mobs or os.environ.get("AGENT_VALIDATION_SKIP_MOBS", "").strip() in (
        "1",
        "true",
        "yes",
    )
    only_ids = [s.strip() for s in args.only.split(",") if s.strip()]
    if args.refill_strip and not only_ids:
        raise SystemExit("--refill-strip requires --only id1,id2,...")
    if args.gold_only and (only_ids or args.refill_strip):
        raise SystemExit("--gold-only cannot combine with --only / --refill-strip")

    # Console-only populate — never require or teleport a player.
    operator_label = "console"
    print(f"QA populate: console agent-paste-at (world={QA_WORLD}); no player teleports")

    if args.resign_signs:
        prior = _load_prior_cells()
        print(f"\n[resign] updating {len(prior)} oak signs from docs/QA_GRID.json")
        n = resign_all_signs(prior)
        print(f"[resign] wrote {n}/{len(prior)} signs (title / id / ★ gold)")
        return

    # Large pad carves need headroom beyond Paper's default 32768/cmd.
    _rcon_retry("gamerule max_block_modifications 100000000", timeout=30)

    probe = _rcon("agent-paste-at", timeout=10) or ""
    if "Unknown or incomplete command" in probe:
        raise SystemExit(
            "agent-paste-at is not registered. Deploy the plugin "
            "(make plugin) and re-run make qa-grid."
        )

    ox, oy, oz = GRID_ORIGIN
    summoned: list[str] = []
    mob_fails: list[tuple[str, str]] = []

    if args.retry_failed:
        print("\n[retry] re-pasting failed cells only (campus kept; no player TP)")
        prior = _load_prior_cells()
        paste_results = retry_failed(prior)
    elif args.refill_strip:
        print(
            f"\n[refill] selective strip at {REFILL_ORIGIN} "
            f"(campus keepers untouched; no player TP)"
        )
        print(f"  ids: {', '.join(only_ids)}")
        template_catalog.reload_catalog()
        by_id = {m.id: m for m in template_catalog.iter_templates()}
        missing = [tid for tid in only_ids if tid not in by_id]
        if missing:
            raise SystemExit(f"unknown template ids: {missing}")
        metas = [by_id[tid] for tid in only_ids]
        packed = pack_campus(metas, origin=REFILL_ORIGIN, row_base=REFILL_ROW_BASE)
        bx1, bz1, bx2, bz2 = campus_bounds(packed)
        max_fh = max((p.fh for p in packed), default=48)
        clear_top = _pad_clear_top(max_fh, REFILL_ORIGIN[1])
        pad_x1 = bx1 - PAD_BORDER
        pad_z1 = bz1 - 16
        pad_x2 = bx2 + PAD_BORDER
        pad_z2 = bz2 + PAD_BORDER
        if args.skip_prepare:
            print(f"  --skip-prepare: keeping pad ({pad_x1},{pad_z1})..({pad_x2},{pad_z2})")
        else:
            print(
                f"  carving refill strip only "
                f"({pad_x1},{pad_z1})..({pad_x2},{pad_z2}) Y={REFILL_ORIGIN[1]}"
            )
            _prepare_flat_area(
                pad_x1,
                pad_z1,
                pad_x2,
                pad_z2,
                surface_y=REFILL_ORIGIN[1],
                clear_height=clear_top - REFILL_ORIGIN[1],
            )
        print(f"\n[refill] pasting {len(packed)} templates via agent-paste-at")
        new_results = paste_all(packed)
        prior = _load_prior_cells()
        paste_results = merge_qa_cells(prior, new_results)
        print(
            f"[refill] merged index: {len(prior)} prior → {len(paste_results)} cells "
            f"({len(new_results)} strip pastes)"
        )
        skip_mobs = True
    else:
        template_catalog.reload_catalog()
        metas = list(template_catalog.iter_templates())
        if args.gold_only:
            gold = _gold_ids()
            metas = [m for m in metas if m.id in gold]
            if not metas:
                raise SystemExit("no gold:true templates in catalog")
            print(
                f"\n[gold-only] {len(metas)} gold templates "
                f"(skipping non-gold; full pad wipe + replace index)"
            )
        if only_ids:
            by_id = {m.id: m for m in metas}
            missing = [tid for tid in only_ids if tid not in by_id]
            if missing:
                raise SystemExit(f"unknown template ids: {missing}")
            metas = [by_id[tid] for tid in only_ids]
            print(f"\n[only] selective re-paste on campus layout for: {', '.join(only_ids)}")
        packed = pack_campus(metas)
        n_templates = len(packed)
        bx1, bz1, bx2, bz2 = campus_bounds(packed)
        span_x = bx2 - bx1 + 1
        span_z = bz2 - bz1 + 1
        max_fh = max((p.fh for p in packed), default=48)
        clear_top = _pad_clear_top(max_fh, oy)
        n_rows = max((p.row for p in packed), default=-1) + 1

        print(f"\n[1/3] preparing elevated artificial pad around {GRID_ORIGIN}")
        print(
            f"  shelf pack: {n_templates} cells, {n_rows} shelves, "
            f"row_budget={ROW_BUDGET}, span ~{span_x}×{span_z}"
        )
        # Expand pad to cover the prior fixed-stride campus (~360×396) so old
        # overlapping neighbor pastes are fully voided before re-paste.
        pad_x1 = min(bx1, ox) - PAD_BORDER
        pad_z1 = min(bz1, oz) - PAD_BORDER
        pad_x2 = max(bx2, ox + 360) + PAD_BORDER
        pad_z2 = max(bz2, oz + 396) + PAD_BORDER
        # Also cover prior QA_GRID campus AABB (gold-only / full re-runs).
        if args.gold_only or not only_ids:
            prior_sidecar = QA_GRID_PATH.with_suffix(".json")
            if prior_sidecar.is_file():
                try:
                    prior_raw = json.loads(prior_sidecar.read_text(encoding="utf-8"))
                    pb = prior_raw.get("bounds") or []
                    if len(pb) == 4:
                        pad_x1 = min(pad_x1, int(pb[0]) - PAD_BORDER)
                        pad_z1 = min(pad_z1, int(pb[1]) - PAD_BORDER)
                        pad_x2 = max(pad_x2, int(pb[2]) + PAD_BORDER)
                        pad_z2 = max(pad_z2, int(pb[3]) + PAD_BORDER)
                        print(
                            f"  prior campus wipe cover bounds "
                            f"{pb[0]},{pb[1]}..{pb[2]},{pb[3]}"
                        )
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
        if only_ids:
            # Selective campus paste: clear only the packed cells' AABB, not whole campus.
            pad_x1 = bx1 - 8
            pad_z1 = bz1 - 8
            pad_x2 = bx2 + 8
            pad_z2 = bz2 + 8
        if args.skip_prepare:
            print(
                f"  --skip-prepare: keeping existing pad "
                f"({pad_x1},{pad_z1})..({pad_x2},{pad_z2}) Y={oy}"
            )
        else:
            print(
                f"  carving void Y={PAD_CLEAR_BOTTOM}..{clear_top} "
                f"over ({pad_x1},{pad_z1})..({pad_x2},{pad_z2}) — batched fills, no player"
            )
            _prepare_flat_area(
                pad_x1, pad_z1, pad_x2, pad_z2, surface_y=oy, clear_height=clear_top - oy
            )
        print(
            f"  footprint campus ready: bounds ({bx1},{bz1})..({bx2},{bz2}), "
            f"pad Y={oy}, cleared to Y={clear_top}"
        )

        if not skip_mobs and not only_ids and not args.gold_only:
            print("\n[2/3] preparing grounded mob pen")
            cx, cy, cz = PEN_CENTER
            _prepare_flat_area(
                cx - PEN_RADIUS,
                cz - PEN_RADIUS,
                cx + PEN_RADIUS,
                cz + PEN_RADIUS,
                surface_y=cy,
            )
        else:
            print("\n[2/3] skipping mob pen (--skip-mobs or selective)")

        print(f"\n[3/3] pasting templates via agent-paste-at ({n_templates})")
        new_results = paste_all(packed)
        if only_ids:
            prior = _load_prior_cells()
            paste_results = merge_qa_cells(prior, new_results)
        else:
            paste_results = new_results

        if not skip_mobs and not only_ids and not args.gold_only:
            print("\n[mobs] summoning supported entities")
            summoned, mob_fails = _spawn_supported_mobs()

    index_path = write_qa_grid(paste_results, player=operator_label)
    print(f"\nQA index written: {index_path}")

    total = len(paste_results)
    ok = sum(1 for r in paste_results if r.ok)
    verified = sum(1 for r in paste_results if r.verified)
    plugin_v = sum(1 for r in paste_results if r.plugin_verified)
    fail = [r for r in paste_results if not r.ok]
    x1, z1, x2, z2 = campus_bounds(
        [
            PackedCell(
                template_id=r.template_id,
                row=r.row,
                col=r.col,
                stand_x=r.stand_x,
                stand_y=r.stand_y,
                stand_z=r.stand_z,
                min_x=r.min_x,
                max_x=r.max_x,
                min_z=r.min_z,
                max_z=r.max_z,
                reserved_w=r.reserved_w,
                reserved_d=r.reserved_d,
                fw=r.fw,
                fh=r.fh,
                fd=r.fd,
            )
            for r in paste_results
            if r.reserved_w > 0
        ]
    )
    span_x = max(0, x2 - x1 + 1)
    span_z = max(0, z2 - z1 + 1)
    print("\n=== SUMMARY ===")
    print(f"templates pasted   {ok}/{total}")
    print(f"  plugin verified  {plugin_v}")
    print(f"  world verified   {verified} (plugin + footprint non-air)")
    print(f"  failed           {len(fail)}")
    print(f"grid origin        {GRID_ORIGIN}")
    print(f"layout             shelf pack row_budget={ROW_BUDGET} aisle={CELL_AISLE}")
    print(f"span               {span_x}×{span_z} bounds ({x1},{z1})..({x2},{z2})")
    print(f"QA index           {index_path}")
    print("player teleports   none (console paste-at)")
    cathedral = next((r for r in paste_results if r.template_id == "gothic_cathedral"), None)
    if cathedral:
        print(
            f"cathedral cell     stand=({cathedral.stand_x},{cathedral.stand_y},"
            f"{cathedral.stand_z}) exclusive=({cathedral.min_x},{cathedral.min_z})"
            f"..({cathedral.max_x},{cathedral.max_z}) "
            f"{'OK' if cathedral.ok else 'FAIL'} non_air={cathedral.non_air}"
        )
    if fail:
        print("template failures:")
        for r in fail:
            print(f"  - {r.template_id}: {r.error} (non_air={r.non_air})")
    if not skip_mobs and not args.retry_failed:
        print(f"mobs summoned      {len(summoned)}/{len(_MOB_LIST)}")
        if mob_fails:
            print("mob failures:")
            for m, e in mob_fails:
                print(f"  - {m}: {e}")
    payload = {
        "templates": {
            "total": total,
            "ok": ok,
            "verified": verified,
            "failures": [asdict(r) for r in fail],
        },
        "mobs": {
            "summoned": summoned,
            "failed": mob_fails,
            "skipped": skip_mobs or args.retry_failed,
        },
        "qa_grid": str(index_path),
        "origin": list(GRID_ORIGIN),
        "layout": "shelf",
        "row_budget": ROW_BUDGET,
        "span": [span_x, span_z],
        "bounds": [x1, z1, x2, z2],
        "player_teleports": False,
        "paste_command": "agent-paste-at",
    }
    print("\n--- summary json ---")
    print(json.dumps(payload, indent=2)[:2000])


if __name__ == "__main__":
    main()
