"""Footprint-aware QA campus shelf packing (no overlap)."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.full_validation import (
    CELL_AISLE,
    ROW_BUDGET,
    campus_bounds,
    cell_reserved_size,
    pack_campus,
)


def _meta(tid: str, fw: int, fh: int, fd: int):
    return SimpleNamespace(id=tid, footprint=(fw, fh, fd))


def test_cell_reserved_covers_facing_extent():
    # Cathedral-class depth must reserve facing clearance + full depth + aisle.
    cw, cd = cell_reserved_size(147, 85)
    assert cw == 147 + 2 * CELL_AISLE
    assert cd >= (85 // 2) + 2 + 85 + CELL_AISLE
    assert cd >= 85 + 12 + CELL_AISLE


def test_shelf_pack_no_overlap_and_megas_exclusive():
    metas = [
        _meta("a_small", 7, 5, 7),
        _meta("b_small", 9, 4, 9),
        _meta("gothic_cathedral", 147, 133, 85),
        _meta("c_small", 5, 3, 5),
        _meta("giant_flower_house", 128, 88, 128),
        _meta("large_spruce_house", 83, 43, 107),
        _meta("mossy_hobbit_hole", 112, 64, 96),
        _meta("d_small", 11, 6, 11),
    ]
    packed = pack_campus(metas, origin=(20000, 120, 20000))
    assert len(packed) == len(metas)

    rects = [(p.min_x, p.min_z, p.max_x, p.max_z, p.template_id) for p in packed]
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            overlap = a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]
            assert not overlap, f"{a[4]} overlaps {b[4]}"

    by_id = {p.template_id: p for p in packed}
    cath = by_id["gothic_cathedral"]
    assert cath.reserved_w >= 147
    assert cath.reserved_d >= 85
    # Stand centered in reserved width; paste goes +Z into the exclusive rect.
    assert cath.min_x <= cath.stand_x <= cath.max_x
    assert cath.min_z <= cath.stand_z <= cath.max_z
    for other in packed:
        if other.template_id == "gothic_cathedral":
            continue
        assert not (
            other.min_x <= cath.max_x
            and cath.min_x <= other.max_x
            and other.min_z <= cath.max_z
            and cath.min_z <= other.max_z
        )

    x1, z1, x2, z2 = campus_bounds(packed)
    assert x2 - x1 + 1 <= ROW_BUDGET + 160  # megas may widen a shelf
    assert z2 > z1


def test_row_wrap_respects_budget():
    # Many medium cells should wrap rather than exceed budget by much.
    metas = [_meta(f"t{i}", 20, 5, 20) for i in range(30)]
    packed = pack_campus(metas, origin=(0, 120, 0))
    assert max(p.row for p in packed) >= 1
    for p in packed:
        # No cell starts past budget except a lone oversized cell.
        assert p.min_x == 0 or p.min_x < ROW_BUDGET + p.reserved_w
