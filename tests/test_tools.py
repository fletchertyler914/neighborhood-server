"""Tests for agent tools (dry-run, no Docker required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.tools import execute_tool, _volume, Vec3


def test_execute_tool_dry_run():
    r = execute_tool(
        "build_platform",
        {
            "center_x": 0,
            "y": 80,
            "center_z": 0,
            "width": 5,
            "depth": 5,
            "block": "quartz_block",
        },
        dry_run=True,
    )
    assert r.ok
    assert "dry-run" in r.output


def test_volume_guard_math():
    assert _volume(Vec3(0, 0, 0), Vec3(9, 9, 9)) == 1000


def test_unknown_tool():
    r = execute_tool("not_a_tool", {}, dry_run=True)
    assert not r.ok
