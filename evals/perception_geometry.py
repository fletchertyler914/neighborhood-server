"""Offline mirror of bounded opening detection for synthetic perception gates."""

from __future__ import annotations

from dataclasses import dataclass

SCAN_HORIZONTAL = 48
MAX_OPENING_LENGTH = 48
SCAN_VERTICAL = 128


@dataclass(frozen=True)
class Opening:
    axis: str
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int
    max_z: int
    length: int
    height: int
    air_cells: int
    confidence: str


def _solid(grid: dict[tuple[int, int, int], str], x: int, y: int, z: int) -> bool:
    return (x, y, z) in grid


def _measure_up(grid: dict[tuple[int, int, int], str], x: int, y: int, z: int) -> int:
    up = 0
    yy = y + 1
    while yy <= y + SCAN_VERTICAL and _solid(grid, x, yy, z):
        up += 1
        yy += 1
    return up


def _measure_down(grid: dict[tuple[int, int, int], str], x: int, y: int, z: int) -> int:
    down = 0
    yy = y - 1
    while yy >= y - SCAN_VERTICAL and _solid(grid, x, yy, z):
        down += 1
        yy -= 1
    return down


def find_opening(
    grid: dict[tuple[int, int, int], str],
    *,
    start: tuple[int, int, int],
    step: tuple[int, int],
) -> Opening | None:
    sx, sy, sz = start
    step_x, step_z = step
    distance = 1
    while distance <= SCAN_HORIZONTAL:
        x = sx + step_x * distance
        z = sz + step_z * distance
        if not _solid(grid, x, sy, z):
            break
        distance += 1
    air_start = distance
    saw_air = False
    far: tuple[int, int, int] | None = None
    for distance in range(air_start, SCAN_HORIZONTAL + 1):
        x = sx + step_x * distance
        z = sz + step_z * distance
        if not _solid(grid, x, sy, z):
            saw_air = True
            continue
        if saw_air and distance - air_start >= 1:
            far = (x, sy, z)
            break
        return None
    if far is None:
        return None
    fx, fy, fz = far
    if grid.get((sx, sy, sz)) != grid.get((fx, fy, fz)):
        return None
    down_s = _measure_down(grid, sx, sy, sz)
    down_f = _measure_down(grid, fx, fy, fz)
    up_s = _measure_up(grid, sx, sy, sz)
    up_f = _measure_up(grid, fx, fy, fz)
    min_y = min(sy - down_s, fy - down_f)
    max_y = max(sy + up_s, fy + up_f)
    height = max(2, min(SCAN_VERTICAL, max_y - min_y + 1))
    along_x = step_z == 0
    min_x, max_x = sorted((sx, fx))
    min_z, max_z = sorted((sz, fz))
    length = (max_x - min_x + 1) if along_x else (max_z - min_z + 1)
    if length < 2 or length > MAX_OPENING_LENGTH:
        return None
    air_cells = 0
    span_cells = 0
    for y in range(min_y, min_y + height):
        if along_x:
            for x in range(min_x, max_x + 1):
                span_cells += 1
                if not _solid(grid, x, y, min_z):
                    air_cells += 1
        else:
            for z in range(min_z, max_z + 1):
                span_cells += 1
                if not _solid(grid, min_x, y, z):
                    air_cells += 1
    if air_cells == 0:
        return None
    if span_cells > 0 and air_cells * 100 // span_cells < 35:
        return None
    confidence = "high" if air_cells >= 8 and length >= 3 and height >= 3 else "medium"
    return Opening(
        axis="x" if along_x else "z",
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=min_y + height - 1,
        min_z=min_z,
        max_z=max_z,
        length=length,
        height=height,
        air_cells=air_cells,
        confidence=confidence,
    )


def build_u_shape(
    *,
    width: int,
    height: int,
    depth: int,
    material: str = "oak_planks",
) -> dict[tuple[int, int, int], str]:
    """Three walls of a box with +Z face open."""
    grid: dict[tuple[int, int, int], str] = {}
    for y in range(height):
        for x in range(width):
            grid[(x, y, 0)] = material  # back
        for z in range(depth):
            grid[(0, y, z)] = material  # left
            grid[(width - 1, y, z)] = material  # right
    return grid


def generate_synthetic_scenes(count: int = 40) -> list[dict]:
    scenes: list[dict] = []
    sizes = [
        (5, 4, 5),
        (7, 6, 7),
        (9, 8, 9),
        (11, 12, 8),
        (15, 20, 10),
        (21, 40, 12),
        (31, 64, 16),
        (41, 40, 20),
    ]
    materials = ["oak_planks", "stone", "quartz_block", "cobblestone", "bricks"]
    idx = 0
    while len(scenes) < count:
        width, height, depth = sizes[idx % len(sizes)]
        material = materials[idx % len(materials)]
        grid = build_u_shape(width=width, height=height, depth=depth, material=material)
        # Look at left-front corner; scan +X across the open face.
        start = (0, max(0, height // 3), depth - 1)
        opening = find_opening(grid, start=start, step=(1, 0))
        scenes.append(
            {
                "id": f"synth.open_face.{idx:02d}",
                "kind": "open_face",
                "width": width,
                "height": height,
                "depth": depth,
                "material": material,
                "start": start,
                "expect": None
                if opening is None
                else {
                    "axis": opening.axis,
                    "length": opening.length,
                    "height": opening.height,
                    "min_y": 0,
                    "air_cells_min": max(1, opening.air_cells // 2),
                    "confidence_in": ["high", "medium"],
                },
            }
        )
        idx += 1
    # Ambiguous / no-opening scenes
    for offset in range(4):
        scenes[-(offset + 1)]["kind"] = "solid_cube"
        scenes[-(offset + 1)]["id"] = f"synth.solid.{offset:02d}"
        w = 4 + offset
        opening = find_opening(
            {(x, y, z): "stone" for x in range(w) for y in range(w) for z in range(w)},
            start=(0, 0, 0),
            step=(1, 0),
        )
        scenes[-(offset + 1)]["expect"] = None if opening is None else scenes[-(offset + 1)]["expect"]
        scenes[-(offset + 1)]["_grid_mode"] = "solid"
        scenes[-(offset + 1)]["width"] = w
    return scenes[:count]


def evaluate_scene(scene: dict) -> tuple[bool, str]:
    if scene.get("_grid_mode") == "solid":
        w = int(scene["width"])
        grid = {(x, y, z): "stone" for x in range(w) for y in range(w) for z in range(w)}
        opening = find_opening(grid, start=(0, 0, 0), step=(1, 0))
        if opening is None:
            return True, "no_opening"
        return False, f"unexpected_opening length={opening.length}"
    grid = build_u_shape(
        width=int(scene["width"]),
        height=int(scene["height"]),
        depth=int(scene["depth"]),
        material=str(scene["material"]),
    )
    start = tuple(scene["start"])
    opening = find_opening(grid, start=start, step=(1, 0))  # type: ignore[arg-type]
    expect = scene.get("expect")
    if expect is None:
        return opening is None, "expected_none"
    if opening is None:
        return False, "missing_opening"
    if opening.axis != expect["axis"]:
        return False, f"axis={opening.axis}"
    if opening.length != expect["length"]:
        return False, f"length={opening.length}"
    if opening.height < expect["height"]:
        return False, f"height={opening.height}"
    if opening.min_y != expect.get("min_y", opening.min_y):
        return False, f"min_y={opening.min_y}"
    if opening.air_cells < expect["air_cells_min"]:
        return False, f"air={opening.air_cells}"
    if opening.confidence not in expect["confidence_in"]:
        return False, f"confidence={opening.confidence}"
    return True, "ok"
