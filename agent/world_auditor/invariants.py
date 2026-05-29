"""Structural invariants over world snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent.world_auditor.snapshot import AIR_BLOCKS, SnapshotBox, WorldSnapshot


@dataclass(frozen=True)
class InvariantResult:
    name: str
    ok: bool
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {"name": self.name, "ok": self.ok, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


def verify_structure(
    check: str,
    snapshot: WorldSnapshot,
    *,
    block: str | None = None,
    min_count: int | None = None,
    min_ratio: float | None = None,
    entity: str | None = None,
    radius: int = 16,
) -> InvariantResult:
    if check == "min_palette_coverage":
        return min_palette_coverage(snapshot, block=block, min_count=min_count, min_ratio=min_ratio)
    if check == "footprint_filled_ratio":
        return footprint_filled_ratio(snapshot, min_ratio=min_ratio or 0.25)
    if check == "wall_perimeter":
        return wall_perimeter(snapshot, block=block)
    if check == "no_floating_blocks":
        return no_floating_blocks(snapshot)
    if check == "entity_count":
        if entity is None:
            return InvariantResult(check, False, "entity_count requires entity")
        return entity_count(snapshot.box, entity=entity, min_count=min_count or 1, radius=radius)
    return InvariantResult(check, False, f"unknown structural check {check!r}")


def _normalize_block(block: str | None) -> str | None:
    if not block:
        return None
    return block if ":" in block else f"minecraft:{block}"


def _is_solid(block: str) -> bool:
    return block not in AIR_BLOCKS


def min_palette_coverage(
    snapshot: WorldSnapshot,
    *,
    block: str | None,
    min_count: int | None = None,
    min_ratio: float | None = None,
) -> InvariantResult:
    wanted = _normalize_block(block)
    if wanted:
        count = snapshot.palette.get(wanted, 0)
    else:
        count = sum(v for k, v in snapshot.palette.items() if _is_solid(k))
    needed = min_count if min_count is not None else 1
    ratio_ok = True
    ratio = count / max(1, snapshot.block_count)
    if min_ratio is not None:
        ratio_ok = ratio >= min_ratio
    ok = count >= needed and ratio_ok
    return InvariantResult(
        "min_palette_coverage",
        ok,
        f"{wanted or 'non_air'} count={count}, ratio={ratio:.3f}",
        {"block": wanted, "count": count, "min_count": needed, "ratio": ratio},
    )


def footprint_filled_ratio(snapshot: WorldSnapshot, *, min_ratio: float) -> InvariantResult:
    filled = sum(v for k, v in snapshot.palette.items() if _is_solid(k))
    ratio = filled / max(1, snapshot.block_count)
    return InvariantResult(
        "footprint_filled_ratio",
        ratio >= min_ratio,
        f"filled={filled}/{snapshot.block_count} ratio={ratio:.3f}",
        {"filled": filled, "total": snapshot.block_count, "ratio": ratio, "min_ratio": min_ratio},
    )


def wall_perimeter(snapshot: WorldSnapshot, *, block: str | None = None) -> InvariantResult:
    if not snapshot.sparse:
        return InvariantResult("wall_perimeter", False, "wall_perimeter requires sparse snapshot")
    wanted = _normalize_block(block)
    box = snapshot.box.normalize()
    perimeter = 0
    hits = 0
    y = box.y1
    for x in range(box.x1, box.x2 + 1):
        for z in (box.z1, box.z2):
            perimeter += 1
            current = snapshot.block_at(x, y, z)
            if (wanted and current == wanted) or (not wanted and _is_solid(current)):
                hits += 1
    for z in range(box.z1 + 1, box.z2):
        for x in (box.x1, box.x2):
            perimeter += 1
            current = snapshot.block_at(x, y, z)
            if (wanted and current == wanted) or (not wanted and _is_solid(current)):
                hits += 1
    ratio = hits / max(1, perimeter)
    return InvariantResult(
        "wall_perimeter",
        ratio >= 0.75,
        f"perimeter hits={hits}/{perimeter} ratio={ratio:.3f}",
        {"hits": hits, "perimeter": perimeter, "ratio": ratio},
    )


def no_floating_blocks(snapshot: WorldSnapshot) -> InvariantResult:
    if not snapshot.sparse:
        return InvariantResult("no_floating_blocks", False, "no_floating_blocks requires sparse snapshot")
    floating = 0
    for (x, y, z), block in snapshot.sparse.items():
        if not _is_solid(block):
            continue
        below = snapshot.sparse.get((x, y - 1, z), "minecraft:air")
        if below in AIR_BLOCKS and y > snapshot.box.normalize().y1:
            floating += 1
    return InvariantResult(
        "no_floating_blocks",
        floating == 0,
        f"floating_blocks={floating}",
        {"floating_blocks": floating},
    )


def entity_count(box: SnapshotBox, *, entity: str, min_count: int, radius: int = 16) -> InvariantResult:
    from agent import tools as T

    n = box.normalize()
    cx = (n.x1 + n.x2) // 2
    cy = (n.y1 + n.y2) // 2
    cz = (n.z1 + n.z2) // 2
    entity_id = entity if ":" in entity else f"minecraft:{entity}"
    out = T._rcon(
        f"execute positioned {cx} {cy} {cz} run execute if entity "
        f"@e[type={entity_id},distance=..{radius},limit={max(min_count, 1)}]",
        timeout=15,
    )
    passed = "passed" in (out or "").lower()
    count_estimate = _parse_entity_count(out)
    ok = passed if count_estimate is None else count_estimate >= min_count
    return InvariantResult(
        "entity_count",
        ok,
        f"{entity_id} near bbox center -> {out[:80]}",
        {"entity": entity_id, "min_count": min_count, "count_estimate": count_estimate},
    )


def _parse_entity_count(output: str | None) -> int | None:
    if not output:
        return None
    m = re.search(r"(\d+)", output)
    return int(m.group(1)) if m else None
