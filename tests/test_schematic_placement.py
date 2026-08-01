"""Placement clearance math mirroring SchematicPlacement.java.

Policy: refuse-don't-build-bad — overlap → no origin; clear in-front → ok.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

PLAYER_MARGIN = 2
UNSAFE_MESSAGE = "I can't build there — look at an open spot and try again."
OVERLAP_MESSAGE = "You're in the way — step aside and try again."


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

    def valid(self) -> bool:
        return self.width >= 1 and self.depth >= 1 and (self.max_y - self.min_y + 1) >= 1


# castle_small_keep after ground-gap compaction: W=19 H=13 L=21, Offset≈[-9,-3,3]
CASTLE = Footprint(min_x=-9, min_y=-3, min_z=3, max_x=9, max_y=9, max_z=23)


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


def facing_offset_origin(
    px: int, py: int, pz: int, dir_x: float, dir_z: float, fp: Footprint
) -> tuple[int, int, int] | None:
    along_x = abs(dir_x) > abs(dir_z)
    clearance = half_extent_clearance(fp, along_x)
    if along_x:
        target_x = px + clearance - fp.min_x if dir_x >= 0 else px - clearance - fp.max_x
        target_z = pz - fp.center_z
    else:
        target_x = px - fp.center_x
        target_z = pz + clearance - fp.min_z if dir_z >= 0 else pz - clearance - fp.max_z
    target_y = py - 1 - fp.min_y
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
) -> tuple[int, int, int] | None:
    if not fp.valid():
        return None
    if gaze is not None:
        hit_x, hit_y, hit_z, face = gaze
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
    facing = facing_offset_origin(px, py, pz, dir_x, dir_z, fp)
    if facing is not None and not footprint_overlaps_player(facing, fp, px, py, pz):
        return facing
    return None


def test_overlap_gaze_on_feet_refuses_gaze() -> None:
    assert (
        gaze_aware_origin(100, 63, 200, "UP", 100, 64, 200, 100, 64, 200, CASTLE)
        is None
    )


def test_old_centered_gaze_would_overlap() -> None:
    """Pre-fix UP centering entombs the player — documented regression."""
    hit_x, hit_y, hit_z = 100, 63, 200
    ox = hit_x - CASTLE.center_x
    oz = hit_z - CASTLE.center_z
    oy = hit_y + 1 - CASTLE.min_y
    assert footprint_overlaps_player((ox, oy, oz), CASTLE, 100, 64, 200)


@pytest.mark.parametrize("dir_x,dir_z", [(0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)])
def test_clear_in_front_facing_is_ok(dir_x: float, dir_z: float) -> None:
    origin = facing_offset_origin(100, 64, 200, dir_x, dir_z, CASTLE)
    assert origin is not None
    assert not footprint_overlaps_player(origin, CASTLE, 100, 64, 200)
    along_x = abs(dir_x) > abs(dir_z)
    clearance = half_extent_clearance(CASTLE, along_x)
    if along_x:
        if dir_x >= 0:
            assert origin[0] + CASTLE.min_x >= 100 + clearance
        else:
            assert origin[0] + CASTLE.max_x <= 100 - clearance
    else:
        if dir_z >= 0:
            assert origin[2] + CASTLE.min_z >= 200 + clearance
        else:
            assert origin[2] + CASTLE.max_z <= 200 - clearance


def test_gaze_on_feet_falls_back_to_clear_facing() -> None:
    origin = resolve_origin(
        px=100,
        py=64,
        pz=200,
        dir_x=0.0,
        dir_z=1.0,
        fp=CASTLE,
        gaze=(100, 63, 200, "UP"),
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


def test_resolve_refuses_invalid_footprint() -> None:
    bad = Footprint(5, 0, 5, 4, 0, 4)  # max < min → invalid
    assert resolve_origin(
        px=0, py=64, pz=0, dir_x=0.0, dir_z=1.0, fp=bad, gaze=None
    ) is None


def test_unsafe_message_is_kid_friendly() -> None:
    assert UNSAFE_MESSAGE == "I can't build there — look at an open spot and try again."
    assert OVERLAP_MESSAGE == "You're in the way — step aside and try again."
    assert "footprint" not in UNSAFE_MESSAGE.lower()
    assert "origin" not in UNSAFE_MESSAGE.lower()
    assert UNSAFE_MESSAGE != OVERLAP_MESSAGE
