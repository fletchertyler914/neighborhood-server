from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from agent.eval.assertions import AssertionFailure
from agent.eval.case import WorldExpect
from agent import tools as T


PASSABLE_BLOCKS = {"air", "cave_air", "void_air"}


def _normalize_block_id(block: str) -> str:
    s = (block or "").strip()
    if not s:
        return ""
    return s if ":" in s else f"minecraft:{s}"


def block_is(x: int, y: int, z: int, block: str) -> bool:
    """Return True if the block at (x,y,z) matches the given block id.

    Uses `execute if block` which works for plain blocks (unlike
    `data get block`, which only returns NBT for block entities).
    """

    block_id = _normalize_block_id(block)
    if not block_id:
        return False
    out = rcon(f"execute if block {x} {y} {z} {block_id}")
    return "passed" in (out or "").lower()


def block_is_passable(x: int, y: int, z: int) -> bool:
    """True if the block is one of the air variants (player can stand in it)."""

    for tag in PASSABLE_BLOCKS:
        if block_is(x, y, z, tag):
            return True
    return False


@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    z1: int
    x2: int
    y2: int
    z2: int

    def normalize(self) -> "Box":
        return Box(
            x1=min(self.x1, self.x2),
            y1=min(self.y1, self.y2),
            z1=min(self.z1, self.z2),
            x2=max(self.x1, self.x2),
            y2=max(self.y1, self.y2),
            z2=max(self.z1, self.z2),
        )

    def iter_xyz(self) -> list[tuple[int, int, int]]:
        n = self.normalize()
        out: list[tuple[int, int, int]] = []
        for x in range(n.x1, n.x2 + 1):
            for y in range(n.y1, n.y2 + 1):
                for z in range(n.z1, n.z2 + 1):
                    out.append((x, y, z))
        return out


def rcon(cmd: str, *, timeout: int = 30) -> str:
    return T._rcon(cmd, timeout=timeout)


def _player_pos(player: str) -> tuple[int, int, int] | None:
    pos_out = rcon(f"data get entity {T._quote_player(player)} Pos")
    import re

    m = re.search(r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]", pos_out or "")
    if not m:
        return None
    x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return int(math.floor(x)), int(math.floor(y)), int(math.floor(z))


def is_player_buried(player: str) -> bool:
    pos = _player_pos(player)
    if pos is None:
        return False
    bx, by, bz = pos
    # Buried means both feet- and head-block are non-passable (solid).
    return (not block_is_passable(bx, by, bz)) and (not block_is_passable(bx, by + 1, bz))


def has_escape_path(player: str, *, radius: int = 6) -> bool:
    pos = _player_pos(player)
    if pos is None:
        return False
    sx, sy, sz = pos

    def passable(px: int, py: int, pz: int) -> bool:
        return block_is_passable(px, py, pz) and block_is_passable(px, py + 1, pz)

    if not passable(sx, sy, sz):
        return False

    # BFS on x/z plane at y=sy, requiring 2-high air.
    start = (sx, sz)
    seen = {start}
    q = [start]
    while q:
        cx, cz = q.pop(0)
        if abs(cx - sx) >= radius or abs(cz - sz) >= radius:
            return True
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = cx + dx, cz + dz
            key = (nx, nz)
            if key in seen:
                continue
            if abs(nx - sx) > radius or abs(nz - sz) > radius:
                continue
            if passable(nx, sy, nz):
                seen.add(key)
                q.append(key)
    return False


def clear_box(box: Box) -> None:
    b = box.normalize()
    rcon(f"fill {b.x1} {b.y1} {b.z1} {b.x2} {b.y2} {b.z2} air replace", timeout=60)


def assert_blocks_present(specs: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for s in specs:
        x, y, z = int(s["x"]), int(s["y"]), int(s["z"])
        block = str(s["block"])
        if not block_is(x, y, z, block):
            failures.append(f"expected {_normalize_block_id(block)} at {x},{y},{z}")
    return failures


def assert_blocks_absent(specs: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for s in specs:
        x, y, z = int(s["x"]), int(s["y"]), int(s["z"])
        block = str(s["block"])
        if block_is(x, y, z, block):
            failures.append(f"expected not {_normalize_block_id(block)} at {x},{y},{z} but found it")
    return failures


def assert_world(expect: WorldExpect, *, player: str) -> list[AssertionFailure]:
    failures: list[AssertionFailure] = []

    for msg in assert_blocks_present(expect.blocks_present):
        failures.append(AssertionFailure(kind="blocks_present", message=msg))

    for msg in assert_blocks_absent(expect.blocks_absent):
        failures.append(AssertionFailure(kind="blocks_absent", message=msg))

    if expect.player_not_buried is True and is_player_buried(player):
        failures.append(
            AssertionFailure(
                kind="player_not_buried",
                message=f"player {player} is buried",
            )
        )

    if expect.player_has_escape_path is not None:
        radius = int(expect.player_has_escape_path.get("radius", 6))
        if not has_escape_path(player, radius=radius):
            failures.append(
                AssertionFailure(
                    kind="player_has_escape_path",
                    message=f"player {player} has no escape path within radius {radius}",
                )
            )

    return failures

