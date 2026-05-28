"""Tests for agent safety helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.safety import is_destructive_tool, guard_rcon_command


def test_destructive_clear_box():
    assert is_destructive_tool("clear_box", {"x1": 0, "y1": 0, "z1": 0, "x2": 1, "y2": 1, "z2": 1})


def test_destructive_fawe_regen():
    assert is_destructive_tool(
        "fawe_as_player", {"player": ".Test", "command": "//regen"}
    )


def test_safe_build_platform():
    assert not is_destructive_tool(
        "build_platform",
        {"center_x": 0, "y": 80, "center_z": 0, "width": 5, "depth": 5, "block": "quartz_block"},
    )


def test_rcon_deny_stop():
    try:
        guard_rcon_command("stop")
        assert False, "expected PermissionError"
    except PermissionError:
        pass
