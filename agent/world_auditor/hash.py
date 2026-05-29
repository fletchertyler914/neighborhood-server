"""Stable content hashes for world snapshots."""

from __future__ import annotations

import hashlib
import json

from agent.world_auditor.snapshot import WorldSnapshot


def content_hash(snapshot: WorldSnapshot, *, include_positions: bool = True) -> str:
    """Return a deterministic SHA-256 over palette and optional block positions."""

    payload: dict[str, object] = {
        "bbox": list(snapshot.box.as_tuple()),
        "palette": dict(sorted(snapshot.palette.items())),
    }
    if include_positions and snapshot.sparse:
        payload["blocks"] = [
            [x, y, z, block]
            for (x, y, z), block in sorted(snapshot.sparse.items())
        ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
