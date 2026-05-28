from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.assertions import assert_spec, normalize_tool_calls
from agent.eval.case import SpecExpect, ToolCallExpectation


def test_normalize_tool_calls_sorts_arguments():
    calls = [{"name": "set_time", "arguments": {"z": 1, "a": 2}}]

    assert normalize_tool_calls(calls)[0]["arguments"] == {"a": 2, "z": 1}


def test_spec_must_call_matches_argument_subset():
    failures = assert_spec(
        expect=SpecExpect(
            status="done",
            must_call=[
                ToolCallExpectation(
                    name="build_platform",
                    arguments={"block": "quartz_block"},
                )
            ],
        ),
        actual_status="done",
        actual_steps=2,
        tool_calls=[
            {
                "name": "build_platform",
                "arguments": {
                    "center_x": 0,
                    "y": 80,
                    "center_z": 0,
                    "width": 5,
                    "depth": 5,
                    "block": "quartz_block",
                },
            }
        ],
    )

    assert failures == []


def test_spec_forbidden_tool_fails():
    failures = assert_spec(
        expect=SpecExpect(forbidden_tools=["clear_box"]),
        actual_status="done",
        actual_steps=1,
        tool_calls=[{"name": "clear_box", "arguments": {}}],
    )

    assert failures
    assert failures[0].kind == "forbidden_tool"

