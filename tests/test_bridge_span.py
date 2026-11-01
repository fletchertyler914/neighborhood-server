"""Bridge/road/path span math mirroring BridgeSpan.java + place_shape routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from companion.place_routing import is_fancy_bridge_template, route_place_shape
from companion.routing import route, wants_clear_site

MAX_LENGTH = 1024
DEFAULT_BRIDGE_LENGTH = 24
DEFAULT_PATH_LENGTH = 48
TINY_GAP_TEMPLATE_MAX = 12
MAX_STEP = 1


class Kind(Enum):
    LAND = "land"
    WATER = "water"
    GAP = "gap"
    LAVA = "lava"


@dataclass(frozen=True)
class Column:
    kind: Kind
    surface_y: int
    solid_top_y: int

    def is_crossing(self) -> bool:
        return self.kind in {Kind.WATER, Kind.GAP, Kind.LAVA}

    @staticmethod
    def land(solid_top_y: int) -> Column:
        return Column(Kind.LAND, solid_top_y, solid_top_y)

    @staticmethod
    def water(surface_y: int, solid_top_y: int) -> Column:
        return Column(Kind.WATER, surface_y, solid_top_y)


@dataclass(frozen=True)
class Result:
    start_dist: int
    end_dist: int
    deck_y: int
    crossed_gap: bool
    found_far_shore: bool

    @property
    def length(self) -> int:
        return self.end_dist - self.start_dist + 1

    def tiny_gap_fits_template(self) -> bool:
        return self.crossed_gap and self.length <= TINY_GAP_TEMPLATE_MAX


def _clamp_len(length: int) -> int:
    return max(2, min(MAX_LENGTH, length))


def _deck_y_for_crossing(
    columns: list[Column], cross_start: int, cross_end: int, fallback: int
) -> int:
    vals = [
        columns[i].surface_y
        for i in range(cross_start, cross_end + 1)
        if columns[i].kind in {Kind.WATER, Kind.GAP}
    ]
    return sum(vals) // len(vals) if vals else fallback


def _shore_near_deck(col: Column, deck_y: int) -> bool:
    return col.kind == Kind.LAND and abs(col.surface_y - deck_y) <= 4


def resolve_bridge(
    columns: list[Column], explicit_length: int | None, fallback_deck_y: int
) -> Result | None:
    result = _resolve(columns, explicit_length, fallback_deck_y, bridge_mode=True)
    if result is None:
        return None
    if result.crossed_gap and not result.found_far_shore and explicit_length is None:
        return None
    return result


def resolve_path(
    columns: list[Column], explicit_length: int | None, fallback_deck_y: int
) -> Result | None:
    return _resolve(columns, explicit_length, fallback_deck_y, bridge_mode=False)


def walkable_profile(
    columns: list[Column], start_dist: int, end_dist: int, seed_y: int
) -> list[int]:
    ys: list[int] = []
    prev = seed_y
    for i in range(end_dist - start_dist + 1):
        col = columns[start_dist - 1 + i]
        target = col.surface_y
        if target > prev + MAX_STEP:
            nxt = prev + MAX_STEP
        elif target < prev - MAX_STEP:
            nxt = prev - MAX_STEP
        else:
            nxt = target
        ys.append(nxt)
        prev = nxt
    return ys


def _resolve(
    columns: list[Column],
    explicit_length: int | None,
    fallback_deck_y: int,
    *,
    bridge_mode: bool,
) -> Result | None:
    if not columns:
        default = DEFAULT_BRIDGE_LENGTH if bridge_mode else DEFAULT_PATH_LENGTH
        length = _clamp_len(explicit_length or default)
        return Result(1, length, fallback_deck_y, False, True)

    n = len(columns)
    cross_start = next((i for i, c in enumerate(columns) if c.is_crossing()), -1)
    if cross_start >= 0 and (bridge_mode or cross_start <= 2):
        cross_end = cross_start
        land_end = -1
        for i in range(cross_start, n):
            if columns[i].is_crossing():
                cross_end = i
            elif columns[i].kind == Kind.LAND:
                land_end = i
                break
            else:
                break
        deck_y = _deck_y_for_crossing(columns, cross_start, cross_end, fallback_deck_y)
        start_idx = cross_start
        if cross_start > 0 and _shore_near_deck(columns[cross_start - 1], deck_y):
            start_idx = cross_start - 1
        found_shore = land_end >= 0 and _shore_near_deck(columns[land_end], deck_y)
        end_idx = land_end if found_shore else cross_end
        start_dist = start_idx + 1
        end_dist = end_idx + 1
        if explicit_length is not None:
            end_dist = min(n, start_dist + _clamp_len(explicit_length) - 1)
            return Result(start_dist, end_dist, deck_y, True, found_shore)
        if not found_shore:
            if bridge_mode:
                return None
            end_dist = max(0, cross_start - 1) + 1
            if end_dist < 1:
                return None
            return Result(1, end_dist, fallback_deck_y, False, False)
        return Result(start_dist, end_dist, deck_y, True, True)

    default = DEFAULT_BRIDGE_LENGTH if bridge_mode else DEFAULT_PATH_LENGTH
    length = _clamp_len(explicit_length or default)
    length = min(length, n)
    deck_y = fallback_deck_y
    for i in range(length):
        if columns[i].kind == Kind.LAND:
            deck_y = columns[i].surface_y
            break
    return Result(1, length, deck_y, False, True)


def _ocean_columns(
    *,
    land_before: int,
    water: int,
    land_after: int,
    shore_y: int = 63,
    water_y: int = 62,
    near_land_y: int | None = None,
) -> list[Column]:
    near_y = shore_y if near_land_y is None else near_land_y
    cols: list[Column] = [Column.land(near_y) for _ in range(land_before)]
    cols.extend(Column.water(water_y, water_y - 8) for _ in range(water))
    cols.extend(Column.land(shore_y) for _ in range(land_after))
    return cols


def test_span_connects_shores_at_water_surface() -> None:
    cols = _ocean_columns(land_before=2, water=40, land_after=5, shore_y=63, water_y=62)
    result = resolve_bridge(cols, None, fallback_deck_y=80)
    assert result is not None
    assert result.crossed_gap
    assert result.found_far_shore
    assert result.deck_y == 62
    assert result.start_dist == 2
    assert result.end_dist == 43
    assert result.length == 42


def test_elevated_pad_not_used_as_near_shore() -> None:
    cols = _ocean_columns(
        land_before=3, water=30, land_after=4, shore_y=63, water_y=62, near_land_y=80
    )
    result = resolve_bridge(cols, None, fallback_deck_y=80)
    assert result is not None
    assert result.deck_y == 62
    assert result.start_dist == 4
    assert result.end_dist == 34


def test_no_far_shore_without_length_fails() -> None:
    cols = _ocean_columns(land_before=1, water=80, land_after=0)
    assert resolve_bridge(cols, None, fallback_deck_y=63) is None
    forced = resolve_bridge(cols, 40, fallback_deck_y=63)
    assert forced is not None
    assert forced.length == 40


def test_tiny_gap_flag() -> None:
    cols = _ocean_columns(land_before=1, water=6, land_after=2)
    result = resolve_bridge(cols, None, fallback_deck_y=63)
    assert result is not None
    assert result.tiny_gap_fits_template()


def test_walkable_profile_terraces_steep_hill() -> None:
    cols = [
        Column.land(70),
        Column.land(70),
        Column.land(75),  # +5 cliff
        Column.land(76),
        Column.land(76),
    ]
    ys = walkable_profile(cols, 1, 5, seed_y=70)
    assert ys[0] == 70
    assert ys[1] == 70
    assert ys[2] == 71  # only +1
    assert ys[3] == 72
    assert ys[4] == 73


def test_land_path_default_length() -> None:
    cols = [Column.land(70) for _ in range(80)]
    result = resolve_path(cols, None, fallback_deck_y=70)
    assert result is not None
    assert not result.crossed_gap
    assert result.length == DEFAULT_PATH_LENGTH


def test_route_make_a_bridge_is_place_shape() -> None:
    for prompt in (
        "make a bridge",
        "build a bridge please",
        "bridge across the water",
        "oak bridge",
        "cobble bridge 5 wide",
    ):
        decision = route(prompt, "job-bridge")
        assert decision.action is not None, prompt
        assert decision.action.tool == "place_shape", prompt
        assert decision.action.arguments["kind"] == "bridge", prompt


def test_route_pave_a_road() -> None:
    for prompt in (
        "pave a road",
        "make a road across",
        "cobble road",
    ):
        decision = route(prompt, "job-road")
        assert decision.action is not None, prompt
        assert decision.action.tool == "place_shape", prompt
        assert decision.action.arguments["kind"] == "road", prompt


def test_route_clear_a_path_trail() -> None:
    for prompt, material in (
        ("clear a path", "dirt_path"),
        ("make a trail", "dirt_path"),
        ("footpath", "dirt_path"),
        ("gravel path 80 long", "gravel"),
        ("path 80 long", "dirt_path"),
    ):
        decision = route(prompt, "job-path")
        assert decision.action is not None, prompt
        assert decision.action.tool == "place_shape", prompt
        assert decision.action.arguments["kind"] == "path", prompt
        assert decision.action.arguments.get("material") == material, (prompt, decision.action.arguments)
        if "80" in prompt:
            assert decision.action.arguments.get("length") == 80, prompt


def test_clear_a_path_does_not_force_clear_site() -> None:
    assert not wants_clear_site("clear a path")
    decision = route("clear a path", "job-cs")
    assert decision.action is not None
    assert decision.action.arguments.get("clear_site") is not True


def test_path_too_long_clarifies() -> None:
    decision = route("path 2000 long", "job-long")
    assert decision.action is None
    assert "1024" in (decision.message or "")


def test_fancy_bridges_still_paste_templates() -> None:
    assert is_fancy_bridge_template("rope bridge")
    assert not is_fancy_bridge_template("make a bridge")
    decision = route("rope bridge", "job-fancy")
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "bridge_rope"


def test_pave_floor_not_stolen_by_road() -> None:
    decision = route("pave this floor with glass", "job-floor")
    assert decision.action is not None
    assert decision.action.tool == "finish_floor"


def test_route_place_shape_bridge_helper() -> None:
    decision = route_place_shape("make a bridge", "job-x")
    assert decision is not None
    assert decision.route == "pattern.place_bridge"


def test_route_start_finish_mark_path() -> None:
    start = route("start marking a path", "job-mark")
    assert start.action is not None
    assert start.action.tool == "mark_route"
    assert start.action.arguments["action"] == "start"
    assert start.action.arguments["kind"] == "path"

    finish = route("finish the path", "job-fin")
    assert finish.action is not None
    assert finish.action.tool == "mark_route"
    assert finish.action.arguments["action"] == "finish"
    assert finish.action.arguments["kind"] == "path"
    assert finish.action.arguments.get("material") == "dirt_path"

    bridge_start = route("start marking a bridge", "job-b")
    assert bridge_start.action is not None
    assert bridge_start.action.arguments == {"action": "start", "kind": "bridge"}

    bridge_fin = route("finish the bridge with oak", "job-bf")
    assert bridge_fin.action is not None
    assert bridge_fin.action.arguments["action"] == "finish"
    assert bridge_fin.action.arguments["kind"] == "bridge"
    assert bridge_fin.action.arguments.get("material") == "oak_planks"
    assert bridge_fin.action.arguments.get("width") == 3


def test_mark_route_phrasing_variants() -> None:
    """Common kid/adult phrasing for start / finish / cancel marker flow."""
    starts = [
        "start a path",
        "start path",
        "begin a path",
        "lets start a path",
        "let's start a bridge",
        "start a bridge",
        "start a road",
        "mark a path",
        "marking a bridge",
        "make a path with markers",
        "build a bridge with gold blocks",
    ]
    for prompt in starts:
        decision = route(prompt, f"job-s-{prompt}")
        assert decision.action is not None, prompt
        assert decision.action.tool == "mark_route", prompt
        assert decision.action.arguments["action"] == "start", prompt

    finishes = [
        "finish this path",
        "finish path",
        "complete the path",
        "path is done",
        "done with the bridge",
        "I'm done with the path",
        "finish marking",
        "connect the gold",
        "link the markers",
        "trail is finished",
    ]
    for prompt in finishes:
        decision = route(prompt, f"job-f-{prompt}")
        assert decision.action is not None, prompt
        assert decision.action.tool == "mark_route", prompt
        assert decision.action.arguments["action"] == "finish", prompt

    cancel = route("stop marking", "job-cancel")
    assert cancel.action is not None
    assert cancel.action.tool == "mark_route"
    assert cancel.action.arguments["action"] == "cancel"

    # Sized start still means gaze/length place_shape, not markers.
    sized = route("start a path 40 long", "job-sized")
    assert sized.action is not None
    assert sized.action.tool == "place_shape"
    assert sized.action.arguments["kind"] == "path"


def test_finish_mark_path_honors_width() -> None:
    """NL width on finish routes — markers stay centerline; width is build thick."""
    default = route("finish the path", "job-w0")
    assert default.action is not None
    assert default.action.arguments["width"] == 3

    for n in range(1, 9):
        decision = route(f"finish the path {n} wide", f"job-w{n}")
        assert decision.action is not None, n
        assert decision.action.tool == "mark_route", n
        assert decision.action.arguments["action"] == "finish", n
        assert decision.action.arguments["width"] == n, n

    bridge = route("finish the bridge 5 blocks wide with oak", "job-bw")
    assert bridge.action is not None
    assert bridge.action.arguments["width"] == 5
    assert bridge.action.arguments.get("material") == "oak_planks"

    # Clamp above 8
    fat = route("finish the path 12 wide", "job-fat")
    assert fat.action is not None
    assert fat.action.arguments["width"] == 8


def test_make_path_still_place_shape_not_finish() -> None:
    """Gaze/marker-aware place_shape — not mark_route finish."""
    decision = route("make a path", "job-gaze")
    assert decision.action is not None
    assert decision.action.tool == "place_shape"
    assert decision.action.arguments["kind"] == "path"


def test_stairs_to_door_phrasing() -> None:
    for prompt in (
        "build stairs up to the door",
        "stairs to the door",
        "steps up to that doorway",
        "make a staircase to the entrance",
        "oak stairs to the door",
    ):
        decision = route(prompt, f"job-st-{prompt}")
        assert decision.action is not None, prompt
        assert decision.action.tool == "place_shape", prompt
        assert decision.action.arguments["kind"] == "stairs_to", prompt
        assert decision.action.arguments.get("width") == 2, prompt

    oak = route("oak stairs to the door", "job-oak-st")
    assert oak.action is not None
    assert oak.action.arguments.get("material") in {"oak_stairs", "oak_planks"}

    # Path / finish path must not steal stair-to-door.
    path = route("finish the path", "job-not-st")
    assert path.action is not None
    assert path.action.tool == "mark_route"


def test_line_xz_bresenham() -> None:
    """Mirror BridgeSpan.lineXZ for a short diagonal."""
    def line_xz(x0: int, z0: int, x1: int, z1: int) -> list[tuple[int, int]]:
        dx = abs(x1 - x0)
        dz = abs(z1 - z0)
        sx = 1 if x0 < x1 else -1
        sz = 1 if z0 < z1 else -1
        err = dx - dz
        x, z = x0, z0
        out: list[tuple[int, int]] = []
        for _ in range(dx + dz + 1):
            out.append((x, z))
            if x == x1 and z == z1:
                break
            e2 = 2 * err
            if e2 > -dz:
                err -= dz
                x += sx
            if e2 < dx:
                err += dx
                z += sz
        return out

    pts = line_xz(0, 0, 3, 0)
    assert pts[0] == (0, 0) and pts[-1] == (3, 0)
    assert len(pts) == 4


def _clamp_step(prev: int, target: int) -> int:
    if target > prev + MAX_STEP:
        return prev + MAX_STEP
    if target < prev - MAX_STEP:
        return prev - MAX_STEP
    return target


def stair_profile_ground_hug(terrain_y: list[int], start_y: int, end_y: int) -> list[int]:
    """Mirror BridgeSpan.stairProfileGroundHug (terrain follow + suffix ramp)."""
    length = len(terrain_y)
    if length == 0:
        return [start_y]
    ys = [0] * length
    if length == 1:
        ys[0] = end_y
        return ys
    ys[0] = start_y
    for i in range(1, length):
        ys[i] = _clamp_step(ys[i - 1], terrain_y[i])
    grade_at_door = ys[length - 1]
    ramp_len = abs(end_y - grade_at_door)
    ramp_start = max(1, length - ramp_len)
    for i in range(ramp_start, length):
        prev = ys[i - 1]
        rem = length - 1 - i
        if end_y - prev > rem + MAX_STEP:
            target = prev + MAX_STEP
        elif prev - end_y > rem + MAX_STEP:
            target = prev - MAX_STEP
        else:
            target = _clamp_step(prev, end_y)
            grade = terrain_y[i]
            if abs(grade - end_y) <= rem and abs(grade - prev) <= MAX_STEP:
                target = grade
            if abs(target - end_y) > rem:
                target = prev + MAX_STEP if end_y > prev else prev - MAX_STEP
        ys[i] = _clamp_step(prev, target)
    ys[length - 1] = end_y
    if abs(ys[length - 1] - ys[length - 2]) > MAX_STEP:
        ys[length - 1] = _clamp_step(ys[length - 2], end_y)
    for i in range(0, ramp_start):
        if ys[i] < terrain_y[i]:
            prev = start_y if i == 0 else ys[i - 1]
            ys[i] = _clamp_step(prev, terrain_y[i])
            if ys[i] < terrain_y[i]:
                ys[i] = min(terrain_y[i], prev + MAX_STEP)
    for i in range(1, length):
        ys[i] = _clamp_step(ys[i - 1], ys[i])
    if abs(end_y - ys[length - 2]) <= MAX_STEP:
        ys[length - 1] = end_y
    return ys


def ground_hug_ramp_start(terrain_y: list[int], start_y: int, end_y: int) -> int:
    probe = [start_y]
    for i in range(1, len(terrain_y)):
        probe.append(_clamp_step(probe[-1], terrain_y[i]))
    ramp_len = abs(end_y - probe[-1])
    return max(1, len(terrain_y) - ramp_len)


def test_ground_hug_no_trench_when_threshold_one_below() -> None:
    terrain = [65] * 15
    ys = stair_profile_ground_hug(terrain, start_y=65, end_y=64)
    ramp_start = ground_hug_ramp_start(terrain, 65, 64)
    assert ys[0] == 65
    assert ys[-1] == 64
    assert all(y >= terrain[i] for i, y in enumerate(ys) if i < ramp_start)
    assert all(y == 65 for y in ys[:ramp_start])


def test_ground_hug_rises_late_to_elevated_door() -> None:
    terrain = [64] * 20
    ys = stair_profile_ground_hug(terrain, start_y=64, end_y=70)
    assert ys[0] == 64 and ys[-1] == 70
    assert all(y >= 64 for y in ys)
    assert sum(1 for y in ys if y == 64) >= 12


def test_old_end_y_clamp_trenches_ground_hug_does_not() -> None:
    terrain = [70] * 20
    hugged = stair_profile_ground_hug(terrain, start_y=70, end_y=64)
    ramp_start = ground_hug_ramp_start(terrain, 70, 64)
    # Old bug: min(profile[i], endY) flattens the whole approach underground.
    assert ramp_start >= 14
    assert all(hugged[i] >= terrain[i] for i in range(ramp_start))
    assert hugged[-1] == 64


def test_approach_never_under_grade_when_door_below() -> None:
    """Outdoor start above sill: approach stays on grade; only suffix may dip."""
    for start_y, end_y, length in ((65, 64, 15), (70, 64, 20), (68, 64, 16)):
        terrain = [start_y] * length
        hugged = stair_profile_ground_hug(terrain, start_y, end_y)
        ramp_start = ground_hug_ramp_start(terrain, start_y, end_y)
        assert ramp_start >= length - abs(end_y - start_y)
        assert all(hugged[i] >= terrain[i] for i in range(ramp_start)), (
            start_y,
            end_y,
            hugged,
            ramp_start,
        )
        assert hugged[-1] == end_y
        assert all(abs(hugged[i] - hugged[i - 1]) <= MAX_STEP for i in range(1, length))


def test_hard_end_y_clamp_still_the_original_trench() -> None:
    """Document the first bug: min(profile, endY) buries the whole run."""
    length, start_y, end_y = 20, 70, 64
    linear = []
    # crude ±1 lerp like stairProfile
    for i in range(length):
        ideal = start_y + round((end_y - start_y) * (i / (length - 1)))
        linear.append(ideal)
    clamped = [min(y, end_y) for y in linear]
    assert sum(1 for y in clamped if y < start_y) >= 15
    hugged = stair_profile_ground_hug([start_y] * length, start_y, end_y)
    ramp_start = ground_hug_ramp_start([start_y] * length, start_y, end_y)
    assert all(hugged[i] >= start_y for i in range(ramp_start))


def test_flat_equal_threshold_never_underground() -> None:
    terrain = [64] * 12
    ys = stair_profile_ground_hug(terrain, 64, 64)
    assert ys == [64] * 12


def test_stairs_up_never_below_terrain() -> None:
    terrain = [64] * 20
    ys = stair_profile_ground_hug(terrain, 64, 70)
    assert all(y >= t for y, t in zip(ys, terrain))
    assert ys[-1] == 70


def prefer_walk_surface(
    near_y: int, solid_top: int, water_top: int | None, max_drop: int
) -> int:
    """Mirror BridgeSpan.preferWalkSurface."""
    min_walk = near_y - max(0, max_drop)
    solid_under_water = water_top is not None and solid_top < water_top
    if solid_under_water:
        return max(water_top, near_y - 1)
    if solid_top < min_walk:
        return max(min_walk, near_y - 1)
    return solid_top


def trail_follow_y(ramp_y: int, terrain_y: int, crossing: bool, deck_floor: int) -> int:
    """Mirror BridgeSpan.trailFollowY."""
    if crossing:
        return max(ramp_y, max(terrain_y, deck_floor))
    return max(ramp_y, terrain_y)


def test_prefer_walk_surface_rejects_lakebed_under_pier() -> None:
    assert prefer_walk_surface(65, 64, None, 4) == 64
    assert prefer_walk_surface(65, 58, 63, 4) == 64
    assert prefer_walk_surface(63, 50, 62, 4) == 62
    assert prefer_walk_surface(65, 40, None, 4) == 64


def test_trail_follow_never_under_land_grade() -> None:
    assert trail_follow_y(64, 70, False, 64) == 70
    assert trail_follow_y(65, 64, False, 64) == 65
    assert trail_follow_y(63, 62, True, 65) == 65


def test_pier_start_stays_on_planks_through_water_approach() -> None:
    start_y, end_y = 64, 70
    terrain = [64, 64, 64, 64, 64, 65, 66, 67, 68, 69, 70, 70]
    ys = stair_profile_ground_hug(terrain, start_y, end_y)
    ramp_start = ground_hug_ramp_start(terrain, start_y, end_y)
    assert ys[0] == start_y
    assert all(y >= start_y for y in ys)
    assert all(ys[i] >= terrain[i] for i in range(ramp_start))
    assert ys[-1] == end_y


def test_ascending_hill_approach_never_under_standing_surface() -> None:
    start_y, end_y = 64, 72
    terrain = [64, 64, 68, 70, 72, 72, 72, 72, 72, 72]
    ys = stair_profile_ground_hug(terrain, start_y, end_y)
    ramp_start = ground_hug_ramp_start(terrain, start_y, end_y)
    assert ys[0] == start_y
    assert all(ys[i] >= start_y for i in range(ramp_start))
    assert all(abs(ys[i] - ys[i - 1]) <= MAX_STEP for i in range(1, len(ys)))
