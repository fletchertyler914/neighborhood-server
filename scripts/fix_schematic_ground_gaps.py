#!/usr/bin/env python3
"""Detect and repair internal air gaps in curated Sponge v3 schematics.

Seed capture accidentally included the temporary stone platform (y=0) plus a
one-block air gap (y=1) under many buildings. This script:

1. Removes empty Y layers between the lowest and highest solid layers
2. Extends ground-level exterior stair runs down so the bottom step sits on
   the foundation (y=1 above a y=0 solid pad)

Usage:
  python3 scripts/fix_schematic_ground_gaps.py --analyze
  python3 scripts/fix_schematic_ground_gaps.py --fix
  python3 scripts/fix_schematic_ground_gaps.py --check   # exit 1 on gaps
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nbtlib
from nbtlib.tag import ByteArray, Compound, Int, IntArray, Short

REPO = Path(__file__).resolve().parents[1]
SCHEM_DIR = REPO / "agent" / "templates" / "schematics"
AIR = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})


def _base(name: str) -> str:
    return name.split("[", 1)[0]


def _is_air(name: str) -> bool:
    return _base(name) in AIR


def _is_stair(name: str) -> bool:
    return "stairs" in _base(name)


def _decode_varints(data: bytes, count: int) -> list[int]:
    out: list[int] = []
    i = 0
    n = len(data)
    while len(out) < count and i < n:
        value = 0
        shift = 0
        while True:
            b = data[i]
            i += 1
            value |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
            if shift > 35:
                raise ValueError("varint too long")
        out.append(value)
    if len(out) != count:
        raise ValueError(f"expected {count} blocks, got {len(out)}")
    return out


def _encode_varints(indices: list[int]) -> bytes:
    out = bytearray()
    for value in indices:
        v = int(value)
        while v >= 0x80:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        out.append(v)
    return bytes(out)


def _facing_delta(name: str) -> tuple[int, int] | None:
    """Return (dx, dz) of the uphill direction for a bottom stair blockstate."""
    if "half=top" in name:
        return None
    if "facing=north" in name:
        return (0, -1)
    if "facing=south" in name:
        return (0, 1)
    if "facing=west" in name:
        return (-1, 0)
    if "facing=east" in name:
        return (1, 0)
    return None


def load_schem(path: Path) -> dict:
    nbt = nbtlib.load(path)
    root = nbt["Schematic"] if "Schematic" in nbt else nbt
    w, h, l = int(root["Width"]), int(root["Height"]), int(root["Length"])
    offset = [int(x) for x in root.get("Offset", [0, 0, 0])]
    blocks = root["Blocks"]
    palette = {str(k): int(v) for k, v in blocks["Palette"].items()}
    inv = {v: k for k, v in palette.items()}
    volume = w * h * l
    raw = bytes(blocks["Data"])
    indices = list(raw) if len(raw) == volume else _decode_varints(raw, volume)
    return {
        "path": path,
        "nbt": nbt,
        "root": root,
        "w": w,
        "h": h,
        "l": l,
        "offset": offset,
        "palette": palette,
        "inv": inv,
        "indices": indices,
    }


def _idx(w: int, l: int, x: int, y: int, z: int) -> int:
    return x + z * w + y * w * l


def solid_per_y(schem: dict) -> list[int]:
    w, h, l = schem["w"], schem["h"], schem["l"]
    inv = schem["inv"]
    indices = schem["indices"]
    counts = [0] * h
    for y in range(h):
        for z in range(l):
            for x in range(w):
                if not _is_air(inv[indices[_idx(w, l, x, y, z)]]):
                    counts[y] += 1
    return counts


def internal_gaps(solid: list[int]) -> list[int]:
    occupied = [y for y, c in enumerate(solid) if c > 0]
    if not occupied:
        return []
    ymin, ymax = occupied[0], occupied[-1]
    return [y for y in range(ymin, ymax + 1) if solid[y] == 0]


def analyze_file(path: Path) -> dict:
    schem = load_schem(path)
    solid = solid_per_y(schem)
    gaps = internal_gaps(solid)
    return {
        "file": path.name,
        "dims": (schem["w"], schem["h"], schem["l"]),
        "offset": schem["offset"],
        "solid_per_y": solid,
        "internal_gaps": gaps,
    }


def _trim_top_empty(schem: dict) -> None:
    """Drop trailing empty Y layers (cosmetic; keeps Height tight)."""
    solid = solid_per_y(schem)
    if not any(solid):
        return
    max_solid = max(y for y, c in enumerate(solid) if c > 0)
    new_h = max_solid + 1
    if new_h >= schem["h"]:
        return
    w, l = schem["w"], schem["l"]
    schem["indices"] = schem["indices"][: w * new_h * l]
    schem["h"] = new_h


def remove_internal_gaps(schem: dict) -> list[int]:
    """Remove empty Y layers between min and max solid. Returns removed Ys."""
    solid = solid_per_y(schem)
    gaps = internal_gaps(solid)
    if not gaps:
        return []

    w, h, l = schem["w"], schem["h"], schem["l"]
    air_id = schem["palette"].get("minecraft:air")
    if air_id is None:
        air_id = max(schem["palette"].values(), default=-1) + 1
        schem["palette"]["minecraft:air"] = air_id
        schem["inv"][air_id] = "minecraft:air"

    occupied = [y for y, c in enumerate(solid) if c > 0]
    ymin, ymax = occupied[0], occupied[-1]
    # Keep layers below the first solid, every solid layer, and trailing empties
    # above the last solid (trimmed separately).
    keep_ys = [y for y in range(h) if y < ymin or y > ymax or solid[y] > 0]
    removed = [y for y in range(ymin, ymax + 1) if solid[y] == 0]

    new_h = len(keep_ys)
    new_indices = [air_id] * (w * new_h * l)
    for new_y, old_y in enumerate(keep_ys):
        for z in range(l):
            for x in range(w):
                new_indices[_idx(w, l, x, new_y, z)] = schem["indices"][
                    _idx(w, l, x, old_y, z)
                ]
    schem["indices"] = new_indices
    schem["h"] = new_h
    return removed


def _ensure_palette(schem: dict, name: str) -> int:
    if name in schem["palette"]:
        return schem["palette"][name]
    nid = max(schem["palette"].values(), default=-1) + 1
    schem["palette"][name] = nid
    schem["inv"][nid] = name
    return nid


def _expand(schem: dict, pad_x0: int, pad_x1: int, pad_z0: int, pad_z1: int) -> None:
    if pad_x0 == pad_x1 == pad_z0 == pad_z1 == 0:
        return
    w, h, l = schem["w"], schem["h"], schem["l"]
    nw, nl = w + pad_x0 + pad_x1, l + pad_z0 + pad_z1
    air_id = _ensure_palette(schem, "minecraft:air")
    new_indices = [air_id] * (nw * h * nl)
    for y in range(h):
        for z in range(l):
            for x in range(w):
                new_indices[_idx(nw, nl, x + pad_x0, y, z + pad_z0)] = schem["indices"][
                    _idx(w, l, x, y, z)
                ]
    schem["indices"] = new_indices
    schem["w"] = nw
    schem["l"] = nl
    # Offset is min-corner relative to copy origin (min - origin). Expanding
    # the min corner in -X/-Z moves min, so Offset decreases on those axes.
    schem["offset"][0] -= pad_x0
    schem["offset"][2] -= pad_z0


def _stair_cells(schem: dict) -> list[tuple[int, int, int, str]]:
    w, h, l = schem["w"], schem["h"], schem["l"]
    inv = schem["inv"]
    out = []
    for y in range(h):
        for z in range(l):
            for x in range(w):
                name = inv[schem["indices"][_idx(w, l, x, y, z)]]
                if _is_stair(name):
                    out.append((x, y, z, name))
    return out


def extend_ground_stairs(schem: dict) -> int:
    """Extend lowest exterior stair runs down onto the foundation (y=1).

    Returns number of stair blocks added.
    """
    cells = _stair_cells(schem)
    if not cells:
        return 0

    global_min_y = min(y for _, y, _, _ in cells)
    if global_min_y <= 1:
        return 0

    # Only repair the lowest stair elevation band (ground entrances).
    candidates = [(x, y, z, name) for x, y, z, name in cells if y == global_min_y]

    # (state_name, x, y, z) placements in pre-expand coordinates.
    placements: list[tuple[str, int, int, int]] = []
    for x, y, z, name in candidates:
        delta = _facing_delta(name)
        if delta is None:
            continue
        dx, dz = delta
        cy, cx, cz = y, x, z
        while cy > 1:
            cy -= 1
            cx -= dx
            cz -= dz
            placements.append((name, cx, cy, cz))

    if not placements:
        return 0

    min_x = min(px for _, px, _, _ in placements)
    max_x = max(px for _, px, _, _ in placements)
    min_z = min(pz for _, _, _, pz in placements)
    max_z = max(pz for _, _, _, pz in placements)
    pad_x0 = max(0, -min_x)
    pad_z0 = max(0, -min_z)
    pad_x1 = max(0, max_x - (schem["w"] - 1))
    pad_z1 = max(0, max_z - (schem["l"] - 1))
    _expand(schem, pad_x0, pad_x1, pad_z0, pad_z1)

    added = 0
    w, l = schem["w"], schem["l"]
    for name, px, py, pz in placements:
        x = px + pad_x0
        z = pz + pad_z0
        if py < 1:
            continue
        stair_id = _ensure_palette(schem, name)
        cur = schem["inv"][schem["indices"][_idx(w, l, x, py, z)]]
        # Fill air or carve an entrance step through floor/wall edge blocks.
        # Never replace the y=0 foundation pad (guarded by py >= 1 above).
        if cur == name:
            continue
        schem["indices"][_idx(w, l, x, py, z)] = stair_id
        added += 1
    return added


def save_schem(schem: dict) -> None:
    root = schem["root"]
    root["Width"] = Short(schem["w"])
    root["Height"] = Short(schem["h"])
    root["Length"] = Short(schem["l"])
    root["Offset"] = IntArray(schem["offset"])

    # Rewrite palette with compact indices 0..n-1 preserving names.
    # Remap if we added entries with high ids.
    names = list(schem["palette"].keys())
    # Keep stable order: existing order by old id, then new names.
    names.sort(key=lambda n: schem["palette"][n])
    used = set(schem["indices"])
    names = [n for n in names if schem["palette"][n] in used]
    if "minecraft:air" in schem["palette"] and schem["palette"]["minecraft:air"] in used:
        pass
    new_palette = {n: i for i, n in enumerate(names)}
    old_to_new = {schem["palette"][n]: new_palette[n] for n in names}
    remapped = [old_to_new[i] for i in schem["indices"]]

    pal_tag = Compound({n: Int(i) for n, i in new_palette.items()})
    if max(remapped, default=0) < 128:
        data_tag = ByteArray(remapped)
    else:
        data_tag = ByteArray(_encode_varints(remapped))

    root["Blocks"] = Compound({"Palette": pal_tag, "Data": data_tag})
    schem["nbt"].save(schem["path"], gzipped=True)


def fix_file(path: Path) -> dict:
    schem = load_schem(path)
    before_gaps = internal_gaps(solid_per_y(schem))
    height_before = schem["h"]
    removed = remove_internal_gaps(schem)
    stairs_added = extend_ground_stairs(schem)
    _trim_top_empty(schem)
    after_gaps = internal_gaps(solid_per_y(schem))
    changed = bool(removed) or stairs_added > 0 or schem["h"] != height_before
    if changed:
        save_schem(schem)
    return {
        "file": path.name,
        "removed_ys": removed,
        "stairs_added": stairs_added,
        "gaps_before": before_gaps,
        "gaps_after": after_gaps,
        "changed": changed,
    }


def iter_schems() -> list[Path]:
    return sorted(SCHEM_DIR.glob("*.schem"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--analyze", action="store_true", help="Print gap report")
    g.add_argument("--fix", action="store_true", help="Rewrite schematics with gaps removed")
    g.add_argument("--check", action="store_true", help="Exit 1 if any internal gaps remain")
    args = parser.parse_args(argv)

    paths = iter_schems()
    if not paths:
        print(f"No schematics in {SCHEM_DIR}", file=sys.stderr)
        return 2

    if args.analyze:
        gapped = []
        for p in paths:
            info = analyze_file(p)
            if info["internal_gaps"]:
                gapped.append(info)
                print(
                    f"{info['file']}: gaps={info['internal_gaps']} "
                    f"solid_per_y={info['solid_per_y']}"
                )
        print(f"\n{len(gapped)}/{len(paths)} schematics have internal Y gaps")
        return 0

    if args.check:
        bad = []
        for p in paths:
            info = analyze_file(p)
            if info["internal_gaps"]:
                bad.append(info)
        if bad:
            print(f"FAIL: {len(bad)} schematic(s) have internal air gaps:", file=sys.stderr)
            for info in bad:
                print(f"  {info['file']}: gaps={info['internal_gaps']}", file=sys.stderr)
            return 1
        print(f"OK: {len(paths)} schematics have no internal foundation/wall Y gaps")
        return 0

    # --fix
    gap_fixed = 0
    stair_fixed = 0
    unchanged = 0
    for p in paths:
        result = fix_file(p)
        after = analyze_file(p)
        if result["removed_ys"]:
            gap_fixed += 1
        if result["stairs_added"]:
            stair_fixed += 1
        if not result["changed"]:
            unchanged += 1
            continue
        status = "OK" if not after["internal_gaps"] else "STILL_GAPPED"
        print(
            f"{p.name}: removed_ys={result['removed_ys']} "
            f"stairs_added={result['stairs_added']} -> {status} "
            f"solid_per_y={after['solid_per_y']}"
        )
        if after["internal_gaps"]:
            print(f"  WARNING: gaps remain {after['internal_gaps']}", file=sys.stderr)
    print(
        f"\nGap-compacted {gap_fixed}, stairs-extended {stair_fixed}, "
        f"unchanged {unchanged}, total {len(paths)}"
    )
    return 0 if all(not analyze_file(p)["internal_gaps"] for p in paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
