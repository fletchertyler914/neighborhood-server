"""Placement clearance math mirroring SchematicPlacement.java.

Policy: gaze-first when safe; facing near-player fallback; refuse overlap.
Ask-before-clear is a separate native/companion concern.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

PLAYER_MARGIN = 2
MEGA_EXTENT = 40
GAZE_SLACK = 8
UNSAFE_MESSAGE = "I can't build there — step back a bit and try again."
OVERLAP_MESSAGE = "You're in the way — step aside and try again."
CLEAR_ASK_MESSAGE = (
    "I'll need to clear some ground there first — want me to? Try: yes"
)


@dataclass(frozen=True)
class Footprint:
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1

    @property
    def depth(self) -> int:
        return self.max_z - self.min_z + 1

    @property
    def center_x(self) -> int:
        return (self.min_x + self.max_x) // 2

    @property
    def center_z(self) -> int:
        return (self.min_z + self.max_z) // 2

    @property
    def max_horizontal_extent(self) -> int:
        return max(self.width, self.depth)

    def is_mega(self) -> bool:
        return self.max_horizontal_extent >= MEGA_EXTENT

    def valid(self) -> bool:
        return self.width >= 1 and self.depth >= 1 and (self.max_y - self.min_y + 1) >= 1


CASTLE = Footprint(min_x=-9, min_y=-3, min_z=3, max_x=9, max_y=9, max_z=23)
CATHEDRAL = Footprint(min_x=-73, min_y=0, min_z=-42, max_x=73, max_y=132, max_z=42)


def footprint_overlaps_player(
    origin: tuple[int, int, int], fp: Footprint, px: int, py: int, pz: int
) -> bool:
    ox, oy, oz = origin
    world_min_x = ox + fp.min_x - PLAYER_MARGIN
    world_max_x = ox + fp.max_x + PLAYER_MARGIN
    world_min_y = oy + fp.min_y
    world_max_y = oy + fp.max_y
    world_min_z = oz + fp.min_z - PLAYER_MARGIN
    world_max_z = oz + fp.max_z + PLAYER_MARGIN
    horizontal = world_min_x <= px <= world_max_x and world_min_z <= pz <= world_max_z
    vertical = py + 1 >= world_min_y and py <= world_max_y
    return horizontal and vertical


def is_under_or_beside_player(hit_x: int, hit_z: int, px: int, pz: int) -> bool:
    return max(abs(hit_x - px), abs(hit_z - pz)) <= 1


def half_extent_clearance(fp: Footprint, along_x: bool) -> int:
    extent = fp.width if along_x else fp.depth
    return (extent // 2) + PLAYER_MARGIN


def gaze_hit_is_near_enough(
    px: int, pz: int, hit_x: int, hit_z: int, fp: Footprint
) -> bool:
    chebyshev = max(abs(hit_x - px), abs(hit_z - pz))
    max_gaze = half_extent_clearance(fp, fp.width >= fp.depth) + GAZE_SLACK
    return chebyshev <= max_gaze


def facing_offset_origin(
    px: int,
    py: int,
    pz: int,
    dir_x: float,
    dir_z: float,
    fp: Footprint,
    forward_blocks: int | None = None,
) -> tuple[int, int, int] | None:
    along_x = abs(dir_x) > abs(dir_z)
    clearance = (
        forward_blocks
        if forward_blocks is not None and forward_blocks > 0
        else half_extent_clearance(fp, along_x)
    )
    if along_x:
        target_x = px + clearance - fp.min_x if dir_x >= 0 else px - clearance - fp.max_x
        target_z = pz - fp.center_z
    else:
        target_x = px - fp.center_x
        target_z = pz + clearance - fp.min_z if dir_z >= 0 else pz - clearance - fp.max_z
    # Floor at feet Y — sits ON the ground block (not playerY-1 into the pad).
    target_y = py - fp.min_y
    origin = (target_x, target_y, target_z)
    if footprint_overlaps_player(origin, fp, px, py, pz):
        return None
    return origin


def gaze_aware_origin(
    hit_x: int,
    hit_y: int,
    hit_z: int,
    face: str,
    support_x: int,
    support_y: int,
    support_z: int,
    px: int,
    py: int,
    pz: int,
    fp: Footprint,
) -> tuple[int, int, int] | None:
    if not fp.valid():
        return None
    if is_under_or_beside_player(hit_x, hit_z, px, pz):
        return None
    target_x = support_x - fp.center_x
    target_z = support_z - fp.center_z
    target_y = support_y - fp.min_y
    if face == "UP":
        target_y = hit_y + 1 - fp.min_y
        target_x = hit_x - fp.center_x
        target_z = hit_z - fp.center_z
    elif face == "NORTH":
        target_z = hit_z - 1 - fp.max_z
    elif face == "SOUTH":
        target_z = hit_z + 1 - fp.min_z
    elif face == "WEST":
        target_x = hit_x - 1 - fp.max_x
    elif face == "EAST":
        target_x = hit_x + 1 - fp.min_x
    origin = (target_x, target_y, target_z)
    if footprint_overlaps_player(origin, fp, px, py, pz):
        return None
    return origin


def resolve_origin(
    *,
    px: int,
    py: int,
    pz: int,
    dir_x: float,
    dir_z: float,
    fp: Footprint,
    gaze: tuple[int, int, int, str] | None,
    forward_blocks: int | None = None,
) -> tuple[int, int, int] | None:
    if not fp.valid():
        return None
    if gaze is not None:
        hit_x, hit_y, hit_z, face = gaze
        if gaze_hit_is_near_enough(px, pz, hit_x, hit_z, fp):
            sx, sy, sz = hit_x, hit_y, hit_z
            if face == "UP":
                sy += 1
            elif face == "NORTH":
                sz -= 1
            elif face == "SOUTH":
                sz += 1
            elif face == "WEST":
                sx -= 1
            elif face == "EAST":
                sx += 1
            gazed = gaze_aware_origin(
                hit_x, hit_y, hit_z, face, sx, sy, sz, px, py, pz, fp
            )
            if gazed is not None:
                return gazed
    facing = facing_offset_origin(px, py, pz, dir_x, dir_z, fp, forward_blocks)
    if facing is not None and not footprint_overlaps_player(facing, fp, px, py, pz):
        return facing
    return None


def test_overlap_gaze_on_feet_refuses_gaze() -> None:
    assert (
        gaze_aware_origin(100, 63, 200, "UP", 100, 64, 200, 100, 64, 200, CASTLE)
        is None
    )


@pytest.mark.parametrize("dir_x,dir_z", [(0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)])
def test_clear_in_front_facing_is_ok(dir_x: float, dir_z: float) -> None:
    origin = facing_offset_origin(100, 64, 200, dir_x, dir_z, CASTLE)
    assert origin is not None
    assert not footprint_overlaps_player(origin, CASTLE, 100, 64, 200)


def test_facing_floor_sits_on_pad_not_sunk() -> None:
    """Schem floor at feet Y (on pad), not playerY-1 (inset into ground)."""
    origin = facing_offset_origin(100, 120, 200, 0.0, 1.0, CASTLE)
    assert origin is not None
    floor_y = origin[1] + CASTLE.min_y
    assert floor_y == 120
    # Matches UP-face on grass at y=119 (pad top).
    gaze = gaze_aware_origin(100, 119, 220, "UP", 100, 120, 220, 100, 120, 200, CASTLE)
    assert gaze is not None
    assert gaze[1] + CASTLE.min_y == 120


def test_gaze_on_feet_falls_back_to_clear_facing() -> None:
    origin = resolve_origin(
        px=100, py=64, pz=200, dir_x=0.0, dir_z=1.0, fp=CASTLE, gaze=(100, 63, 200, "UP")
    )
    assert origin is not None
    assert not footprint_overlaps_player(origin, CASTLE, 100, 64, 200)


def test_resolve_never_returns_overlapping_origin() -> None:
    for gaze in (None, (100, 63, 200, "UP"), (100, 63, 205, "UP"), (110, 63, 220, "UP")):
        origin = resolve_origin(
            px=100, py=64, pz=200, dir_x=0.0, dir_z=1.0, fp=CASTLE, gaze=gaze
        )
        if origin is not None:
            assert not footprint_overlaps_player(origin, CASTLE, 100, 64, 200)


def test_unsafe_and_clear_ask_messages_are_kid_friendly() -> None:
    assert "open spot" not in UNSAFE_MESSAGE.lower()
    assert "footprint" not in CLEAR_ASK_MESSAGE.lower()
    assert "want me to" in CLEAR_ASK_MESSAGE.lower()
    assert "Try: yes" in CLEAR_ASK_MESSAGE


def test_cathedral_is_mega() -> None:
    assert CATHEDRAL.is_mega()
    assert not CASTLE.is_mega()


def test_mega_gaze_preferred_when_safe() -> None:
    """Mega builds still use gaze when the look target keeps the player outside."""
    # Near edge of cathedral depth/2+margin ≈ 44; hit at +50 is within maxGaze.
    hit_z = 200 + 50
    origin = resolve_origin(
        px=100,
        py=64,
        pz=200,
        dir_x=0.0,
        dir_z=1.0,
        fp=CATHEDRAL,
        gaze=(100, 63, hit_z, "UP"),
    )
    assert origin is not None
    assert not footprint_overlaps_player(origin, CATHEDRAL, 100, 64, 200)
    assert origin[2] == hit_z - CATHEDRAL.center_z


def test_forward_blocks_overrides_facing_clearance() -> None:
    origin = facing_offset_origin(0, 64, 0, 0.0, 1.0, CASTLE, forward_blocks=20)
    assert origin is not None
    near_edge = origin[2] + CASTLE.min_z
    assert near_edge == 20


def test_small_nearby_gaze_still_allowed() -> None:
    origin = resolve_origin(
        px=100,
        py=64,
        pz=200,
        dir_x=0.0,
        dir_z=1.0,
        fp=CASTLE,
        gaze=(100, 63, 215, "UP"),
    )
    assert origin is not None
    assert origin[2] == 215 - CASTLE.center_z
