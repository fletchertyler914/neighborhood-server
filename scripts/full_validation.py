"""End-to-end validation: paste every catalog template + summon every supported entity.

Designed to run from inside the mc-agent container (where the deterministic
tools talk to mc-lan via RCON). All actions go through `agent.tools` so
this validates the curated assets consumed by the in-game sidekick.

Layout (dedicated remote pad, far from spawn / normal play):

    Templates: 11-column grid starting at (13000, 96, 13000), spacing 36/64.
               Player TPs onto a solid grass platform in front of each cell.
    Mob pen:   centered around (13000, 96, 14500).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

from agent.templates import catalog as template_catalog
from agent.tools import _rcon, paste_template_at_player, summon_entity, clear_box


def _detect_online_player() -> str:
    """Operator-only — never fall back to a random friend online."""
    preferred = (
        os.environ.get("AGENT_LIVE_PLAYER")
        or os.environ.get("AGENT_VALIDATION_PLAYER")
        or "firecrab93"
    ).strip()
    raw = _rcon("list", timeout=10) or ""
    match = re.search(r"online:?\s*(.+)$", raw, re.I)
    if not match:
        return ""
    names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    for name in names:
        if name.lower() == preferred.lower():
            return name
    return ""


PLAYER = (
    os.environ.get("AGENT_VALIDATION_PLAYER")
    or os.environ.get("AGENT_LIVE_PLAYER")
    or _detect_online_player()
)
if not PLAYER:
    raise SystemExit(
        "validation player firecrab93 is not online. Join as that account "
        "(do not use friends), then re-run, or set AGENT_LIVE_PLAYER=<name>."
    )
# Dedicated remote validation pad (aligned with evals/run_live.py).
GRID_ORIGIN = (13000, 96, 13000)
COL_STRIDE = 36
ROW_STRIDE = 64
COLUMNS = 11

PEN_CENTER = (13000, 96, 14500)
PEN_RADIUS = 60


def _fill_chunked(
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    block: str,
    *,
    chunk_x: int = 24,
    chunk_y: int = 24,
    chunk_z: int = 24,
) -> None:
    """Run vanilla /fill over a large cuboid without hitting command limits."""

    xa, xb = sorted((x1, x2))
    ya, yb = sorted((y1, y2))
    za, zb = sorted((z1, z2))
    for x in range(xa, xb + 1, chunk_x):
        ex = min(x + chunk_x - 1, xb)
        for y in range(ya, yb + 1, chunk_y):
            ey = min(y + chunk_y - 1, yb)
            for z in range(za, zb + 1, chunk_z):
                ez = min(z + chunk_z - 1, zb)
                _rcon(f"fill {x} {y} {z} {ex} {ey} {ez} {block}", timeout=60)


def _prepare_flat_area(
    x1: int,
    z1: int,
    x2: int,
    z2: int,
    *,
    surface_y: int,
    clear_height: int,
) -> None:
    """Carve a solid floating pad and clear only the air above it."""

    _rcon(
        f"forceload add {min(x1, x2)} {min(z1, z2)} {max(x1, x2)} {max(z1, z2)}",
        timeout=60,
    )
    # Clear pad volume then lay thick stone + grass top (feet at surface_y).
    _fill_chunked(
        x1, surface_y - 4, z1, x2, surface_y + clear_height, z2, "air"
    )
    _fill_chunked(x1, surface_y - 4, z1, x2, surface_y - 1, z2, "stone")
    _fill_chunked(x1, surface_y - 1, z1, x2, surface_y - 1, z2, "grass_block")


@dataclass
class CellResult:
    template_id: str
    ok: bool
    used_schematic: bool
    summary: str
    error: str = ""


def _tp_facing_south(x: int, y: int, z: int) -> None:
    # Stand on grass at y-1; ensure a local pad underfoot before each cell TP.
    _rcon(f"fill {x - 1} {y - 1} {z - 1} {x + 1} {y - 1} {z + 1} grass_block")
    _rcon(f"tp {PLAYER} {x + 0.5} {y} {z + 0.5} 0 0")
    time.sleep(0.3)


def paste_all() -> list[CellResult]:
    template_catalog.reload_catalog()
    metas = list(template_catalog.iter_templates())
    results: list[CellResult] = []
    ox, oy, oz = GRID_ORIGIN
    for idx, meta in enumerate(metas):
        col = idx % COLUMNS
        row = idx // COLUMNS
        x = ox + col * COL_STRIDE
        z = oz + row * ROW_STRIDE
        _tp_facing_south(x, oy, z)
        r = paste_template_at_player(PLAYER, meta.id)
        output = (r.output or r.error or "").splitlines()
        head = output[0] if output else ""
        used_schem = head.startswith("pasted template")
        cell = CellResult(
            template_id=meta.id,
            ok=bool(r.ok),
            used_schematic=used_schem,
            summary=head[:120],
            error=(r.error or "")[:200] if not r.ok else "",
        )
        results.append(cell)
        flag = "OK" if r.ok else "X "
        sflag = "S" if used_schem else "F"
        print(f"  [{flag}|{sflag}] {meta.id:30s} ({x},{oy},{z}) {head[:80]}")
    return results


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


def main() -> None:
    print(f"\n[1/3] preparing grounded paste grid around {GRID_ORIGIN}")
    ox, oy, oz = GRID_ORIGIN
    _prepare_flat_area(
        ox - 16,
        oz - 16,
        ox + COLUMNS * COL_STRIDE + 32,
        oz + 10 * ROW_STRIDE + 32,
        surface_y=oy,
        clear_height=48,
    )
    print("  restored grass plane and cleared air above")

    print("\n[2/3] preparing grounded mob pen")
    cx, cy, cz = PEN_CENTER
    _prepare_flat_area(
        cx - PEN_RADIUS,
        cz - PEN_RADIUS,
        cx + PEN_RADIUS,
        cz + PEN_RADIUS,
        surface_y=cy,
        clear_height=12,
    )

    print("\n[3/3] pasting all templates")
    paste_results = paste_all()

    print("\n[mobs] summoning supported entities")
    summoned, mob_fails = _spawn_supported_mobs()

    total = len(paste_results)
    ok = sum(1 for r in paste_results if r.ok)
    schem = sum(1 for r in paste_results if r.used_schematic)
    fail = [r for r in paste_results if not r.ok]
    print("\n=== SUMMARY ===")
    print(f"templates pasted   {ok}/{total}")
    print(f"  via schematic    {schem}")
    print(f"  via fallback     {ok - schem}")
    if fail:
        print("template failures:")
        for r in fail:
            print(f"  - {r.template_id}: {r.error}")
    print(f"mobs summoned      {len(summoned)}/{len(_MOB_LIST)}")
    if mob_fails:
        print("mob failures:")
        for m, e in mob_fails:
            print(f"  - {m}: {e}")
    payload = {
        "templates": {
            "total": total,
            "ok": ok,
            "via_schematic": schem,
            "via_fallback": ok - schem,
            "failures": [r.__dict__ for r in fail],
            "all_results": [r.__dict__ for r in paste_results],
        },
        "mobs": {
            "summoned": summoned,
            "failed": mob_fails,
        },
    }
    print("\n--- full results json (truncated) ---")
    print(json.dumps({"templates": payload["templates"], "mobs": payload["mobs"]}, indent=2)[:1500])


if __name__ == "__main__":
    main()
