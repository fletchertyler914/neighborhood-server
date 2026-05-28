"""Unit tests for template catalog and template tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reload_catalog():
    from agent.templates import catalog as tc

    tc.reload_catalog()
    yield
    tc.reload_catalog()


def test_infer_chicken_coop_from_prompt():
    from agent.templates import catalog as tc

    assert tc.infer_template_from_prompt("make me a chicken coop with 4 chickens") == (
        "chicken_coop_small"
    )


def test_infer_castle_from_prompt():
    from agent.templates import catalog as tc

    assert tc.infer_template_from_prompt("build a stone fortress") == "castle_small_keep"


def test_resolve_alias_and_validate():
    from agent.templates import catalog as tc

    assert tc.resolve_template_id("hen house") == "chicken_coop_small"
    assert tc.validate_template_id("pig_pen_small") == "pig_pen_small"
    with pytest.raises(ValueError, match="unknown"):
        tc.validate_template_id("not_a_real_template")


def test_list_template_summaries_includes_fallback_flag():
    from agent.templates import catalog as tc

    rows = tc.list_template_summaries(category="farm")
    ids = {r["id"] for r in rows}
    assert "chicken_coop_small" in ids
    coop = next(r for r in rows if r["id"] == "chicken_coop_small")
    assert coop["has_fallback"] is True
    # `has_schematic` reflects current repo state — True once `.schem` is
    # committed via the seed pipeline, False otherwise. We just check the
    # key exists and is a bool so the test survives the seed-on-disk flip.
    assert isinstance(coop["has_schematic"], bool)


def test_register_template_entry(tmp_path, monkeypatch):
    from agent.templates import catalog as tc

    cat_copy = tmp_path / "catalog.json"
    cat_copy.write_text(
        json.dumps(
            {
                "version": 1,
                "schematics_namespace": "neighborhood",
                "templates": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tc, "_CATALOG_PATH", cat_copy)
    tc.reload_catalog()

    meta = tc.register_template_entry(
        "test_shack",
        title="Test Shack",
        category="community",
        tags=["shack"],
        footprint=[5, 4, 5],
    )
    assert meta.id == "test_shack"
    assert tc.validate_template_id("test_shack") == "test_shack"


def test_list_templates_tool():
    from agent.tools import list_templates

    result = list_templates(category="farm", tags=["chicken"])
    assert result.ok
    assert "chicken_coop_small" in result.output


def test_paste_template_falls_back_when_no_schematic():
    from agent.tools import PlayerFacing, ToolResult, paste_template_at_player

    facing = PlayerFacing(x=100, y=65, z=200, yaw=0.0, forward_dx=0, forward_dz=1)
    pen_result = ToolResult(tool="build_animal_pen_at_player", ok=True, output="pen")
    mob_result = ToolResult(tool="summon_entity", ok=True, output="mobs")

    stubs = {
        "build_animal_pen_at_player": lambda **_kw: pen_result,
        "summon_entity": lambda *_a, **_kw: mob_result,
    }
    with patch(
        "agent.tools._monolith.template_catalog.schematic_available_on_server",
        return_value=False,
    ), patch(
        "agent.tools._monolith.template_catalog.ensure_schematic_on_server",
        return_value=False,
    ), patch(
        "agent.tools._monolith._player_facing",
        return_value=facing,
    ), patch.dict("agent.tools.TOOL_DISPATCH", stubs):
        result = paste_template_at_player("firecrab93", "chicken_coop_small")
    assert result.ok
    assert "fallback" in (result.output or "").lower()


def test_routing_record_roundtrip():
    from agent.routing_context import finish_job, get_job, start_job

    rec = start_job("job-xyz")
    rec.intent_family = "farm_pen"
    rec.selected_template_id = "chicken_coop_small"
    rec.selected_tool = "paste_template_at_player"
    assert get_job("job-xyz") is rec
    finished = finish_job("job-xyz")
    assert finished is not None
    d = finished.to_dict()
    assert d["intent_family"] == "farm_pen"
    assert d["selected_template_id"] == "chicken_coop_small"
