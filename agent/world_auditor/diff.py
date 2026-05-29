"""Snapshot diff helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from agent.world_auditor.snapshot import WorldSnapshot


@dataclass
class SnapshotDiff:
    before: WorldSnapshot
    after: WorldSnapshot
    palette_added: Counter[str] = field(default_factory=Counter)
    palette_removed: Counter[str] = field(default_factory=Counter)
    changed_blocks: int = 0

    @property
    def volume_delta(self) -> int:
        return sum(self.palette_added.values()) - sum(self.palette_removed.values())

    @property
    def changed_non_air(self) -> int:
        added = sum(v for k, v in self.palette_added.items() if not k.endswith(":air"))
        removed = sum(v for k, v in self.palette_removed.items() if not k.endswith(":air"))
        return added + removed

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": list(self.after.box.as_tuple()),
            "palette_added": dict(sorted(self.palette_added.items())),
            "palette_removed": dict(sorted(self.palette_removed.items())),
            "changed_blocks": self.changed_blocks,
            "volume_delta": self.volume_delta,
            "changed_non_air": self.changed_non_air,
        }


def diff_snapshots(before: WorldSnapshot, after: WorldSnapshot) -> SnapshotDiff:
    added = Counter()
    removed = Counter()
    all_blocks = set(before.palette) | set(after.palette)
    for block in all_blocks:
        delta = after.palette.get(block, 0) - before.palette.get(block, 0)
        if delta > 0:
            added[block] = delta
        elif delta < 0:
            removed[block] = -delta

    changed = 0
    if before.sparse and after.sparse:
        keys = set(before.sparse) | set(after.sparse)
        changed = sum(1 for key in keys if before.sparse.get(key) != after.sparse.get(key))
    else:
        changed = sum(added.values()) + sum(removed.values())

    return SnapshotDiff(
        before=before,
        after=after,
        palette_added=added,
        palette_removed=removed,
        changed_blocks=changed,
    )
