"""Tests for smart context assembly without hitting the live server."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import context as ctx_mod
from agent.context import WorldContext, gather
from agent.job import JobRequest
from agent.orchestrator import _build_smart_context, _is_thinking_model


def test_thinking_model_detection():
    assert _is_thinking_model("qwen3:8b")
    assert _is_thinking_model("qwen3.6:27b")
    assert _is_thinking_model("deepseek-r1:32b")
    assert not _is_thinking_model("llama3.1:8b")
    assert not _is_thinking_model("qwen2.5:14b")


def test_world_context_render():
    wc = WorldContext(
        online_players=[".BedrockTester", "JavaTester"],
        time_of_day="noon",
        facing="south (+Z)",
        ground_block="grass_block",
        ground_y=79,
        last_actions=['"build platform here" -> build_platform'],
    )
    rendered = wc.render()
    assert ".BedrockTester" in rendered
    assert "noon" in rendered
    assert "grass_block" in rendered
    assert "build_platform" in rendered


def test_smart_context_includes_player_and_kb():
    req = JobRequest(
        player=".BedrockTester",
        uuid="00000000-0000-0000-0009-01f42260e0d1",
        x=100.0,
        y=80.0,
        z=-50.0,
        prompt="build a 21x21 quartz platform at my feet",
    )

    fake = WorldContext(
        online_players=[".BedrockTester"],
        time_of_day="noon",
        facing="south (+Z)",
        ground_block="grass_block",
        ground_y=79,
        last_actions=[],
    )
    with patch.object(ctx_mod, "gather", return_value=fake), patch(
        "agent.orchestrator.gather_context", return_value=fake
    ):
        msg = _build_smart_context(req)
    assert ".BedrockTester" in msg
    assert "quartz" in msg.lower() or "platform" in msg.lower()
    assert "Live world context" in msg
