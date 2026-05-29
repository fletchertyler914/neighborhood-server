from __future__ import annotations

from collections import Counter

from agent.world_auditor.diff import diff_snapshots
from agent.world_auditor.hash import content_hash
from agent.world_auditor.invariants import verify_structure
from agent.world_auditor.snapshot import SnapshotBox, WorldSnapshot


def _snapshot(blocks: dict[tuple[int, int, int], str]) -> WorldSnapshot:
    box = SnapshotBox(0, 0, 0, 2, 0, 2)
    palette = Counter(blocks.values())
    return WorldSnapshot(box=box, palette=palette, sparse=blocks, source="test")


def test_snapshot_diff_reports_added_and_changed_blocks():
    before = _snapshot({(0, 0, 0): "minecraft:air", (1, 0, 0): "minecraft:air"})
    after = _snapshot({(0, 0, 0): "minecraft:oak_fence", (1, 0, 0): "minecraft:air"})

    delta = diff_snapshots(before, after)

    assert delta.palette_added["minecraft:oak_fence"] == 1
    assert delta.palette_removed["minecraft:air"] == 1
    assert delta.changed_blocks == 1


def test_content_hash_is_stable_for_same_snapshot():
    snap = _snapshot({(0, 0, 0): "minecraft:stone", (1, 0, 0): "minecraft:air"})

    assert content_hash(snap) == content_hash(snap)
    assert content_hash(snap).startswith("sha256:")


def test_wall_perimeter_invariant_accepts_ring():
    blocks: dict[tuple[int, int, int], str] = {}
    for x in range(3):
        for z in range(3):
            edge = x in (0, 2) or z in (0, 2)
            blocks[(x, 0, z)] = "minecraft:oak_fence" if edge else "minecraft:air"
    snap = _snapshot(blocks)

    result = verify_structure("wall_perimeter", snap, block="oak_fence")

    assert result.ok


def test_min_palette_coverage_counts_requested_block():
    snap = _snapshot(
        {
            (0, 0, 0): "minecraft:stone_bricks",
            (1, 0, 0): "minecraft:stone_bricks",
            (2, 0, 0): "minecraft:air",
        }
    )

    result = verify_structure("min_palette_coverage", snap, block="stone_bricks", min_count=2)

    assert result.ok
