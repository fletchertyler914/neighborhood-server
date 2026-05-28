"""Deterministic template seeding: fallback build → FAWE //schem save → verify.

Pipeline per template:

1. Teleport the seed player into the sandbox at a fixed facing (south, yaw 0).
2. Clear the working volume to air, then drop a temporary platform under it.
3. Run the catalog's ``fallback`` (or ``fallback_steps``) parametric builder.
4. Compute the build's deterministic bounding box from ``meta.footprint`` and
   the same anchor that ``paste_template_at_player`` uses.
5. Issue ``//pos1`` / ``//pos2`` / ``//copy`` / ``//schem save neighborhood/<id>``
   via the ``agentexec`` plugin (so FAWE runs as the player).
6. Verify the ``.schem`` exists on the bind-mounted host repo directory.
7. Optionally clear the build area afterward.

Requires:

* ``AGENT_SEED_PLAYER`` (or ``--player``) — an online opped player whose
  client is connected (FAWE runs as that player).
* The ``NeighborhoodAgent`` Paper plugin loaded (provides ``/agentexec``).
* Bind mount ``./agent/templates/schematics → /data/plugins/FastAsyncWorldEdit/
  schematics/neighborhood``.

Safe to re-run; ``--missing-only`` is the default and skips templates whose
``.schem`` is already on disk.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from agent import tools as T
from agent.executor import execute_tool_deterministic as call
from agent.templates import catalog as template_catalog
from agent.templates.anchor import resolve_step_args
from agent.templates.pack_spec import file_content_hash

_REPO = Path(__file__).resolve().parents[2]
_SEED_X = int(os.environ.get("AGENT_SEED_SANDBOX_X", "9500"))
_SEED_Y = int(os.environ.get("AGENT_SEED_SANDBOX_Y", "90"))
_SEED_Z = int(os.environ.get("AGENT_SEED_SANDBOX_Z", "9500"))
_SEED_PLAYER = os.environ.get("AGENT_SEED_PLAYER", "")
_SEED_FLOOR_BLOCK = os.environ.get("AGENT_SEED_FLOOR_BLOCK", "stone")
_BUILD_SETTLE_SEC = float(os.environ.get("AGENT_SEED_SETTLE_SEC", "0.4"))


def _tp_facing_south(player: str, x: int, y: int, z: int) -> None:
    """Vanilla /tp with yaw=0 (south) and pitch=0 so paste anchor is deterministic."""

    T._rcon(f"tp {T._quote_player(player)} {x} {y} {z} 0 0")


def _box_for_template(meta: template_catalog.TemplateMeta) -> tuple[int, int, int, int, int, int]:
    """Bounding box used by `paste_template_at_player` when the player faces south.

    `paste_template_at_player` computes:
      center_forward = distance_default + max(w, d) // 2
      ax = SEED_X + 0 * center_forward          (south: dx=0)
      ay = SEED_Y - 1
      az = SEED_Z + 1 * center_forward          (south: dz=1)

    The build extends roughly w×h×d around (ax, ay, az). We pad by 1 on
    every side to capture builders that include a base/roof slab outside
    the declared footprint.
    """

    w, h, d = meta.footprint
    dist = meta.distance_default
    center_forward = dist + max(w, d) // 2
    ax = _SEED_X
    ay = _SEED_Y - 1
    az = _SEED_Z + center_forward

    # Builders like `build_house_at_player` use `dist + depth // 2` for the
    # forward anchor (not `max(w, d) // 2`). When w > d that means the actual
    # build sits closer to the seed player than the conservative `max`-based
    # anchor would suggest. Pad the z-axis by half of the (w-d) discrepancy on
    # the near side so the front wall (door + windows) is always captured.
    near_pad = max(1, abs(w - d) // 2 + 1)
    far_pad = 1
    x1 = ax - (w // 2) - 1
    x2 = ax + (w // 2) + 1
    z1 = az - (d // 2) - near_pad
    z2 = az + (d // 2) + far_pad
    y1 = ay - 1
    y2 = ay + h + 2
    return x1, y1, z1, x2, y2, z2


def _agentexec(player: str, fawe_cmd: str) -> str:
    """Run a //... FAWE command as the player via the NeighborhoodAgent plugin."""

    verb = fawe_cmd.lstrip("/")
    cmd = f"agentexec {T._quote_player(player)} //{verb}"
    return T._rcon(cmd, timeout=60)


def _run_fallback(meta: template_catalog.TemplateMeta, player: str, ax: int, ay: int, az: int) -> bool:
    """Run catalog.fallback (or fallback_steps) and return True on success."""

    if meta.fallback_steps:
        for step in meta.fallback_steps:
            stool = str(step.get("tool") or "")
            sargs = resolve_step_args(dict(step.get("args") or {}), ax=ax, ay=ay, az=az)
            sargs.setdefault("player", player)
            r = call(stool, sargs, dry_run=False)
            if not r.ok:
                print(f"    fallback_steps {stool} FAILED: {r.error}")
                return False
        return True
    if not meta.fallback:
        print("    no fallback defined")
        return False
    stool = str(meta.fallback.get("tool") or "")
    sargs = resolve_step_args(dict(meta.fallback.get("args") or {}), ax=ax, ay=ay, az=az)
    sargs.setdefault("player", player)
    r = call(stool, sargs, dry_run=False)
    if not r.ok:
        print(f"    fallback {stool} FAILED: {r.error}")
        return False
    return True


def seed_one(template_id: str, player: str, *, keep_build: bool = False, dry_run: bool = False) -> dict[str, Any]:
    meta = template_catalog.find_template(template_id)
    if dry_run:
        return {"template_id": template_id, "dry_run": True}

    x1, y1, z1, x2, y2, z2 = _box_for_template(meta)
    work_pad = 4
    wx1, wy1, wz1 = x1 - work_pad, y1, z1 - work_pad
    wx2, wy2, wz2 = x2 + work_pad, y2 + 4, z2 + work_pad
    volume = (wx2 - wx1 + 1) * (wy2 - wy1 + 1) * (wz2 - wz1 + 1)
    if volume > 200_000:
        return {"template_id": template_id, "ok": False, "error": f"work volume {volume} exceeds 200k guardrail"}

    _tp_facing_south(player, _SEED_X, _SEED_Y, _SEED_Z)
    time.sleep(_BUILD_SETTLE_SEC)

    r = call("clear_box", {"x1": wx1, "y1": wy1, "z1": wz1, "x2": wx2, "y2": wy2, "z2": wz2}, dry_run=False)
    if not r.ok:
        return {"template_id": template_id, "ok": False, "error": f"clear_box: {r.error}"}

    floor_r = call(
        "build_platform",
        {
            "center_x": (wx1 + wx2) // 2,
            "y": wy1,
            "center_z": (wz1 + wz2) // 2,
            "width": wx2 - wx1 + 1,
            "depth": wz2 - wz1 + 1,
            "block": _SEED_FLOOR_BLOCK,
        },
        dry_run=False,
    )
    if not floor_r.ok:
        return {"template_id": template_id, "ok": False, "error": f"floor: {floor_r.error}"}

    _tp_facing_south(player, _SEED_X, _SEED_Y + 1, _SEED_Z)
    time.sleep(_BUILD_SETTLE_SEC)

    w, h, d = meta.footprint
    dist = meta.distance_default
    center_forward = dist + max(w, d) // 2
    ax = _SEED_X
    ay = _SEED_Y - 1
    az = _SEED_Z + center_forward

    if not _run_fallback(meta, player, ax, ay, az):
        return {"template_id": template_id, "ok": False, "error": "fallback build failed"}

    time.sleep(_BUILD_SETTLE_SEC)

    # `agentexec` returns synchronously to RCON but schedules the actual FAWE
    # command for the next server tick. Without sleeps between, //schem save
    # races ahead of //copy and ships an empty/stale clipboard. A short pause
    # between each step lets FAWE finish on the main thread.
    _FAWE_TICK = float(os.environ.get("AGENT_SEED_FAWE_TICK_SEC", "0.6"))

    out1 = _agentexec(player, f"pos1 {x1},{y1},{z1}")
    time.sleep(_FAWE_TICK)
    out2 = _agentexec(player, f"pos2 {x2},{y2},{z2}")
    time.sleep(_FAWE_TICK)
    out_copy = _agentexec(player, "copy")
    time.sleep(max(1.5, _FAWE_TICK * 2.0))
    save_name = meta.schematic_load_name
    # FAWE's //schem save silently no-ops when the target file already exists
    # (no overwrite by default, and no error surfaced to the player). Delete
    # the existing file first so the save always writes fresh content.
    local = template_catalog.schematic_repo_path(meta)
    if local.is_file():
        try:
            local.unlink()
        except OSError:
            pass
    out_save = _agentexec(player, f"schem save {save_name}")
    time.sleep(max(1.5, _FAWE_TICK * 2.0))

    deadline = time.time() + 10.0
    on_server = False
    local = template_catalog.schematic_repo_path(meta)
    while time.time() < deadline:
        on_server = template_catalog.schematic_available_on_server(meta)
        if on_server and local.is_file():
            break
        time.sleep(0.5)
    local_exists = local.is_file()

    if not (on_server and local_exists):
        return {
            "template_id": template_id,
            "ok": False,
            "error": "schem save did not produce file within 10s",
            "on_server": on_server,
            "local_exists": local_exists,
            "fawe_save_output": (out_save or "")[:200],
            "fawe_pos1": (out1 or "")[:80],
            "fawe_pos2": (out2 or "")[:80],
            "fawe_copy": (out_copy or "")[:80],
        }

    digest = file_content_hash(local)
    if not keep_build:
        call("clear_box", {"x1": wx1, "y1": wy1, "z1": wz1, "x2": wx2, "y2": wy2, "z2": wz2}, dry_run=False)

    return {
        "template_id": template_id,
        "ok": True,
        "size_bytes": local.stat().st_size,
        "content_hash": digest,
        "box": [x1, y1, z1, x2, y2, z2],
        "saved_as": save_name,
    }


def seed_batch(
    *,
    player: str,
    category: str | None = None,
    complexity: str | None = None,
    missing_only: bool = True,
    limit: int = 0,
    keep_build: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in template_catalog.iter_templates(category=category):
        if complexity and meta.complexity != complexity:
            continue
        local = template_catalog.schematic_repo_path(meta)
        if missing_only and local.is_file():
            continue
        result = seed_one(meta.id, player, keep_build=keep_build)
        flag = "OK" if result.get("ok") else "X "
        print(f"  [{flag}] {meta.id}  → {result.get('saved_as', '-')}  ({result.get('error', '')})")
        rows.append(result)
        if limit and len(rows) >= limit:
            break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed templates via fallback builds + FAWE save")
    parser.add_argument("--player", default=_SEED_PLAYER)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--category", default="")
    parser.add_argument("--complexity", default="")
    parser.add_argument("--missing-only", action="store_true", default=True)
    parser.add_argument("--all", action="store_true", help="Re-seed even templates with existing .schem")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keep-build", action="store_true", help="Leave the build in the world after saving")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.player and not args.dry_run:
        raise SystemExit("set AGENT_SEED_PLAYER env var or pass --player")
    missing_only = False if args.all else args.missing_only
    if args.only:
        out = [
            seed_one(tid, args.player, keep_build=args.keep_build, dry_run=args.dry_run)
            for tid in args.only
        ]
    else:
        out = seed_batch(
            player=args.player,
            category=args.category or None,
            complexity=args.complexity or None,
            missing_only=missing_only,
            limit=args.limit,
            keep_build=args.keep_build,
        )
    print(json.dumps({"results": out, "ok": sum(1 for r in out if r.get('ok')), "fail": sum(1 for r in out if not r.get('ok'))}, indent=2))


if __name__ == "__main__":
    main()
