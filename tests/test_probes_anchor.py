"""Tests for build-anchor inference from tool traces."""

from __future__ import annotations

from agent.eval.corpus_case import WorldProbe
from agent.eval.probes import _anchor_from_commands, infer_build_anchor_from_trace


def test_anchor_from_commands_parses_tp_first():
    cmds = [
        "tp JavaTester 10240 -61 10136",
        "agentexec JavaTester //schem load neighborhood/chicken_coop_small",
        "agentexec JavaTester //paste -a",
        "tp JavaTester 10240 -60 10128",
    ]
    assert _anchor_from_commands(cmds) == (10240, -61, 10136)


def test_anchor_from_commands_parses_fill_midpoint():
    cmds = [
        "fill 10333 -61 10131 10339 -61 10137 grass_block replace",
        "fill 10333 -60 10131 10339 -57 10137 air replace",
    ]
    # x: (10333+10339)/2 = 10336, y: -61, z: (10131+10137)/2 = 10134
    assert _anchor_from_commands(cmds) == (10336, -61, 10134)


def test_anchor_from_commands_returns_none_for_irrelevant_input():
    assert _anchor_from_commands([]) is None
    assert _anchor_from_commands(["say hello", "weather clear"]) is None
    assert _anchor_from_commands(None) is None


def test_infer_build_anchor_uses_tp_command_for_paste_template():
    tool_calls = [
        {
            "name": "paste_template_at_player",
            "arguments": {"player": "JavaTester", "template_id": "chicken_coop_small"},
            "result": {
                "ok": True,
                "output": "ran 4 commands",
                "commands": [
                    "tp JavaTester 10240 -61 10136",
                    "agentexec JavaTester //schem load neighborhood/chicken_coop_small",
                    "agentexec JavaTester //paste -a",
                    "tp JavaTester 10240 -60 10128",
                ],
            },
        }
    ]
    anchor = infer_build_anchor_from_trace(
        tool_calls,
        player="JavaTester",
        sandbox_center=(0, 64, 0),
        probe=WorldProbe(kind="structural_check", check="min_palette_coverage", block="oak_fence"),
    )
    assert anchor == (10240, -61, 10136)


def test_infer_build_anchor_uses_fill_midpoint_for_animal_pen():
    tool_calls = [
        {
            "name": "build_animal_pen_at_player",
            "arguments": {"player": "JavaTester", "animal": "chicken"},
            "result": {
                "ok": True,
                "commands": [
                    "fill 10333 -61 10131 10339 -61 10137 grass_block replace",
                    "fill 10333 -60 10131 10339 -57 10137 air replace",
                ],
            },
        }
    ]
    anchor = infer_build_anchor_from_trace(
        tool_calls,
        player="JavaTester",
        sandbox_center=(0, 64, 0),
        probe=WorldProbe(kind="structural_check", check="min_palette_coverage", block="oak_fence"),
    )
    assert anchor == (10336, -61, 10134)


def test_infer_build_anchor_skips_failed_tools():
    tool_calls = [
        {
            "name": "paste_template_at_player",
            "arguments": {"player": "JavaTester", "template_id": "missing"},
            "result": {
                "ok": False,
                "commands": ["tp JavaTester 10 20 30"],
            },
        }
    ]
    anchor = infer_build_anchor_from_trace(
        tool_calls,
        player="JavaTester",
        sandbox_center=(0, 64, 0),
        probe=WorldProbe(kind="structural_check", check="min_palette_coverage"),
    )
    assert anchor is None
