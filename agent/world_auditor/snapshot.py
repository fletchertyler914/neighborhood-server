"""World snapshots from Paper region files, with a small-box RCON fallback."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
DEFAULT_MAX_RCON_BLOCKS = int(os.environ.get("WORLD_AUDITOR_MAX_RCON_BLOCKS", "5000"))


@dataclass(frozen=True)
class SnapshotBox:
    x1: int
    y1: int
    z1: int
    x2: int
    y2: int
    z2: int

    def normalize(self) -> "SnapshotBox":
        return SnapshotBox(
            x1=min(self.x1, self.x2),
            y1=min(self.y1, self.y2),
            z1=min(self.z1, self.z2),
            x2=max(self.x1, self.x2),
            y2=max(self.y1, self.y2),
            z2=max(self.z1, self.z2),
        )

    @property
    def volume(self) -> int:
        n = self.normalize()
        return (n.x2 - n.x1 + 1) * (n.y2 - n.y1 + 1) * (n.z2 - n.z1 + 1)

    def iter_xyz(self):
        n = self.normalize()
        for x in range(n.x1, n.x2 + 1):
            for y in range(n.y1, n.y2 + 1):
                for z in range(n.z1, n.z2 + 1):
                    yield x, y, z

    def as_tuple(self) -> tuple[int, int, int, int, int, int]:
        n = self.normalize()
        return (n.x1, n.y1, n.z1, n.x2, n.y2, n.z2)


@dataclass
class WorldSnapshot:
    box: SnapshotBox
    palette: Counter[str] = field(default_factory=Counter)
    sparse: dict[tuple[int, int, int], str] = field(default_factory=dict)
    source: str = "unknown"
    world_dir: str = ""

    @property
    def block_count(self) -> int:
        return sum(self.palette.values())

    def block_at(self, x: int, y: int, z: int) -> str:
        return self.sparse.get((x, y, z), "minecraft:air")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": list(self.box.as_tuple()),
            "palette": dict(sorted(self.palette.items())),
            "block_count": self.block_count,
            "source": self.source,
            "world_dir": self.world_dir,
        }


def default_world_dir() -> Path:
    configured = os.environ.get("WORLD_AUDITOR_WORLD_DIR")
    if configured:
        return Path(configured)
    if Path("/app/data/world").exists():
        return Path("/app/data/world")
    return Path(__file__).resolve().parents[2] / "data" / "world"


def snapshot_box(
    box: SnapshotBox,
    *,
    world_dir: Path | None = None,
    flush: bool = True,
    include_sparse: bool = True,
    allow_rcon_fallback: bool = True,
    max_rcon_blocks: int = DEFAULT_MAX_RCON_BLOCKS,
    palette_of_interest: list[str] | None = None,
) -> WorldSnapshot:
    """Snapshot a box from Anvil region files, falling back to RCON for small boxes."""

    nbox = box.normalize()
    wdir = world_dir or default_world_dir()
    if flush:
        _flush_world()

    anvil_snap: WorldSnapshot | None = None
    try:
        anvil_snap = _snapshot_box_anvil(nbox, wdir, include_sparse=include_sparse)
        # Anvil-on-disk lags behind FAWE/world edits for chunks still in memory.
        # Treat an all-air result as "not yet persisted" and fall back to RCON.
        non_air = sum(
            count for block, count in anvil_snap.palette.items() if block not in AIR_BLOCKS
        )
        if non_air > 0:
            return anvil_snap
    except Exception:
        if not allow_rcon_fallback:
            raise

    if not allow_rcon_fallback:
        return anvil_snap or WorldSnapshot(box=nbox, source="empty", world_dir=str(wdir))
    if nbox.volume > max_rcon_blocks:
        # Box is too large to RCON-sample; return whatever anvil saw.
        return anvil_snap or WorldSnapshot(box=nbox, source="empty", world_dir=str(wdir))
    return _snapshot_box_rcon(
        nbox,
        wdir,
        include_sparse=include_sparse,
        palette_of_interest=palette_of_interest,
    )


def _normalize_block_id(block: str) -> str:
    raw = (block or "").strip()
    if not raw:
        return "minecraft:air"
    if raw.startswith("Block("):
        raw = raw.removeprefix("Block(").removesuffix(")")
    raw = raw.strip("'\"")
    return raw if ":" in raw else f"minecraft:{raw}"


def _flush_world() -> None:
    try:
        from agent import tools as T

        T._rcon("save-all flush", timeout=60)
    except Exception:
        # Snapshot callers can still read persisted chunks or use synthetic tests.
        pass


def _region_coord(block_coord: int) -> int:
    return math.floor(block_coord / 512)


def _chunk_coord(block_coord: int) -> int:
    return math.floor(block_coord / 16)


def _snapshot_box_anvil(
    box: SnapshotBox,
    world_dir: Path,
    *,
    include_sparse: bool,
) -> WorldSnapshot:
    try:
        import anvil  # type: ignore
    except ImportError as exc:
        raise RuntimeError("anvil-parser2 is not installed") from exc

    region_dir = world_dir / "region"
    if not region_dir.exists():
        raise FileNotFoundError(f"region directory not found: {region_dir}")

    palette: Counter[str] = Counter()
    sparse: dict[tuple[int, int, int], str] = {}
    region_cache: dict[tuple[int, int], Any] = {}
    chunk_cache: dict[tuple[int, int], Any] = {}

    for x, y, z in box.iter_xyz():
        rx, rz = _region_coord(x), _region_coord(z)
        region_path = region_dir / f"r.{rx}.{rz}.mca"
        if not region_path.exists():
            block = "minecraft:air"
        else:
            region = region_cache.get((rx, rz))
            if region is None:
                region = anvil.Region.from_file(str(region_path))
                region_cache[(rx, rz)] = region
            cx, cz = _chunk_coord(x), _chunk_coord(z)
            chunk_key = (cx, cz)
            chunk = chunk_cache.get(chunk_key)
            if chunk is None:
                chunk = anvil.Chunk.from_region(region, cx % 32, cz % 32)
                chunk_cache[chunk_key] = chunk
            try:
                raw = chunk.get_block(x % 16, y, z % 16)
                block = _normalize_block_id(getattr(raw, "id", str(raw)))
            except Exception:
                block = "minecraft:air"
        palette[block] += 1
        if include_sparse:
            sparse[(x, y, z)] = block

    return WorldSnapshot(box=box, palette=palette, sparse=sparse, source="anvil", world_dir=str(world_dir))


def _snapshot_box_rcon(
    box: SnapshotBox,
    world_dir: Path,
    *,
    include_sparse: bool,
    palette_of_interest: list[str] | None = None,
) -> WorldSnapshot:
    """RCON-backed snapshot.

    Vanilla Minecraft has no general "what block is here?" RCON command
    (``data get block`` only returns NBT for block entities). To work around
    this, we use ``execute if block`` against a shortlist of candidate blocks:
    first ``minecraft:air`` to classify air vs structure, then any
    ``palette_of_interest`` so callers can reliably count specific block
    types. Non-air cells we cannot identify are recorded as
    ``minecraft:_unknown_solid`` so structural invariants can still see them.
    """

    from agent import tools as T

    candidate_blocks: list[str] = ["minecraft:air"]
    for raw in palette_of_interest or []:
        normalized = raw if ":" in raw else f"minecraft:{raw}"
        if normalized not in candidate_blocks:
            candidate_blocks.append(normalized)

    palette: Counter[str] = Counter()
    sparse: dict[tuple[int, int, int], str] = {}
    for x, y, z in box.iter_xyz():
        block = "minecraft:_unknown_solid"
        for candidate in candidate_blocks:
            out = T._rcon(
                f"execute if block {x} {y} {z} {candidate}", timeout=10
            )
            if "passed" in (out or "").lower():
                block = candidate
                break
        palette[block] += 1
        if include_sparse:
            sparse[(x, y, z)] = block
    return WorldSnapshot(
        box=box, palette=palette, sparse=sparse, source="rcon", world_dir=str(world_dir)
    )
