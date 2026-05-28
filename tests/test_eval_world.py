from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.case import WorldExpect
from agent.eval.world import assert_world


def test_world_blocks_present_passes():
    with patch("agent.eval.world.block_is", return_value=True):
        failures = assert_world(
            WorldExpect(blocks_present=[{"x": 0, "y": 80, "z": 0, "block": "quartz_block"}]),
            player=".EvalBot",
        )

    assert failures == []


def test_world_blocks_present_fails_when_mismatch():
    with patch("agent.eval.world.block_is", return_value=False):
        failures = assert_world(
            WorldExpect(blocks_present=[{"x": 0, "y": 80, "z": 0, "block": "quartz_block"}]),
            player=".EvalBot",
        )

    assert failures
    assert failures[0].kind == "blocks_present"


def test_world_player_buried_fails():
    with patch("agent.eval.world.is_player_buried", return_value=True):
        failures = assert_world(
            WorldExpect(player_not_buried=True),
            player=".EvalBot",
        )

    assert failures
    assert failures[0].kind == "player_not_buried"

