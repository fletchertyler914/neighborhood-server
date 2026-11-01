"""Ops-gated `/ai ingest` deterministic routing."""

from __future__ import annotations

from companion.ingest_routing import parse_ingest_prompt, route_ingest
from companion.ingest_schem import url_allowlisted
from companion.routing import route


def test_parse_ingest_schemcraft() -> None:
    ask = parse_ingest_prompt(
        "ingest https://www.schemcraft.com/schematics/fantasy-medieval-survival-house"
    )
    assert ask is not None
    assert "schemcraft.com" in ask.url
    assert ask.template_id is None


def test_parse_add_template_as_id() -> None:
    ask = parse_ingest_prompt(
        "add template https://www.schemcraft.com/schematics/barn-with-silo as barn_red_large"
    )
    assert ask is not None
    assert ask.template_id == "barn_red_large"


def test_parse_ingest_trailing_title() -> None:
    ask = parse_ingest_prompt(
        "ingest https://bloxelizer.com/schematics/windmill Small Windmill"
    )
    assert ask is not None
    assert "bloxelizer.com" in ask.url
    assert ask.title == "Small Windmill"
    assert ask.template_id is None


def test_parse_ingest_quoted_title() -> None:
    ask = parse_ingest_prompt(
        'ingest https://bloxelizer.com/schematics/windmill "Harbor lighthouse"'
    )
    assert ask is not None
    assert ask.title == "Harbor lighthouse"


def test_parse_ingest_title_and_as_id() -> None:
    ask = parse_ingest_prompt(
        "ingest https://bloxelizer.com/schematics/windmill Small Windmill as bx_windmill_sm"
    )
    assert ask is not None
    assert ask.title == "Small Windmill"
    assert ask.template_id == "bx_windmill_sm"


def test_parse_ingest_as_id_then_title() -> None:
    ask = parse_ingest_prompt(
        "ingest https://bloxelizer.com/schematics/windmill as bx_windmill_sm Small Windmill"
    )
    assert ask is not None
    assert ask.template_id == "bx_windmill_sm"
    assert ask.title == "Small Windmill"


def test_route_passes_title_slot() -> None:
    decision = route_ingest(
        "ingest https://bloxelizer.com/schematics/windmill Cozy Windmill",
        can_ingest=True,
    )
    assert decision is not None
    assert decision.route == "ops.ingest"
    assert decision.pending_slots is not None
    assert decision.pending_slots["title"] == "Cozy Windmill"


def test_kid_denied() -> None:
    decision = route_ingest(
        "ingest https://www.schemcraft.com/schematics/x",
        can_ingest=False,
    )
    assert decision is not None
    assert decision.route == "ops.ingest.denied"
    assert "adult" in decision.message.lower() or "op" in decision.message.lower()


def test_ops_allowlisted_returns_execute_slots() -> None:
    decision = route(
        "ingest https://www.schemcraft.com/schematics/fantasy-medieval-survival-house",
        "job-ingest",
        can_ingest=True,
    )
    assert decision.route == "ops.ingest"
    assert decision.pending_slots is not None
    assert "schemcraft.com" in decision.pending_slots["url"]


def test_ops_bloxelizer_allowlisted() -> None:
    ok, reason = url_allowlisted("https://bloxelizer.com/schematics/windmill")
    assert ok
    assert "bloxelizer" in reason.lower()
    decision = route_ingest(
        "ingest https://bloxelizer.com/schematics/windmill as smoke_bx_windmill",
        can_ingest=True,
    )
    assert decision is not None
    assert decision.route == "ops.ingest"
    assert decision.pending_slots is not None
    assert "bloxelizer.com" in decision.pending_slots["url"]
    assert decision.pending_slots["template_id"] == "smoke_bx_windmill"


def test_bad_host_rejected() -> None:
    ok, _reason = url_allowlisted("https://evil.example/schem.schem")
    assert ok  # direct .schem OK
    ok2, reason2 = url_allowlisted("https://evil.example/page")
    assert not ok2
    assert "allowlist" in reason2.lower()
    decision = route_ingest(
        "ingest https://evil.example/page",
        can_ingest=True,
    )
    assert decision is not None
    assert decision.route == "ops.ingest.bad_url"
    assert "bloxelizer" in decision.message.lower()


def test_non_ingest_falls_through() -> None:
    decision = route("build me a cottage", "job-build", can_ingest=True)
    assert decision.route != "ops.ingest"
