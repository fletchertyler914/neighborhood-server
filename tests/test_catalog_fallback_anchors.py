"""Catalog invariant: any fallback to an absolute-coord tool needs anchor placeholders."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ABS_COORD_TOOLS = {
    "build_platform": ["center_x", "y", "center_z"],
    "build_sphere": ["center_x", "center_y", "center_z"],
    "build_cylinder": ["center_x", "y", "center_z"],
    "build_spiral_staircase": ["center_x", "y", "center_z"],
    "fill_box": ["x1", "y1", "z1", "x2", "y2", "z2"],
    "clear_box": ["x1", "y1", "z1", "x2", "y2", "z2"],
    "summon_entity": ["x", "y", "z"],
}


def test_every_absolute_coord_fallback_has_coords():
    from agent.templates import catalog as tc

    tc.reload_catalog()
    bad: list[str] = []
    for meta in tc.iter_templates():
        fb = meta.fallback
        if not fb:
            continue
        tool = str(fb.get("tool") or "")
        if tool not in ABS_COORD_TOOLS:
            continue
        args = fb.get("args") or {}
        for k in ABS_COORD_TOOLS[tool]:
            if k not in args:
                bad.append(f"{meta.id}.{tool} missing {k}")
    assert not bad, bad
