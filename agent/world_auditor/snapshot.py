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
) -> WorldSnapshot:
    """Snapshot a box from Anvil region files, falling back to RCON for small boxes."""

    nbox = box.normalize()
    wdir = world_dir or default_world_dir()
    if flush:
        _flush_world()

    try:
        snap = _snapshot_box_anvil(nbox, wdir, include_sparse=include_sparse)
        if snap.block_count:
            return snap
    except Exception:
        if not allow_rcon_fallback:
            raise

    if not allow_rcon_fallback:
        return WorldSnapshot(box=nbox, source="empty", world_dir=str(wdir))
    if nbox.volume > max_rcon_blocks:
        raise ValueError(
            f"RCON fallback refuses {nbox.volume:,} blocks; cap is {max_rcon_blocks:,}"
        )
    return _snapshot_box_rcon(nbox, wdir, include_sparse=include_sparse)


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
) -> WorldSnapshot:
    from agent import tools as T

    palette: Counter[str] = Counter()
    sparse: dict[tuple[int, int, int], str] = {}
    for x, y, z in box.iter_xyz():
        out = T._rcon(f"data get block {x} {y} {z} Name", timeout=15)
        m = re.search(r"minecraft:[a-z0-9_]+", out or "")
        block = m.group(0) if m else "minecraft:air"
        palette[block] += 1
        if include_sparse:
            sparse[(x, y, z)] = block
    return WorldSnapshot(box=box, palette=palette, sparse=sparse, source="rcon", world_dir=str(world_dir))
