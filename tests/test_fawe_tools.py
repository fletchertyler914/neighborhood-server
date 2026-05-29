"""FAWE typed primitive validation (no Docker)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.executor import execute_tool_deterministic
from agent.tool_registry import TOOL_DEFINITIONS_BY_NAME


def test_fawe_primitives_registered():
    expected = {
        "select_box",
        "set_selection",
        "replace_in_selection",
        "undo",
        "redo",
        "generate_forest_at_player",
    }
    missing = expected - set(TOOL_DEFINITIONS_BY_NAME.keys())
    assert not missing, f"missing FAWE tools: {missing}"


def test_select_box_dry_run_schema():
    result = execute_tool_deterministic(
        "select_box",
        {"x1": 0, "y1": 64, "z1": 0, "x2": 10, "y2": 70, "z2": 10, "player": "Steve"},
        dry_run=True,
    )
    assert result.ok
    assert "dry-run" in result.output


def test_undo_requires_player():
    result = execute_tool_deterministic("undo", {"player": "Steve"}, dry_run=True)
    assert result.ok
