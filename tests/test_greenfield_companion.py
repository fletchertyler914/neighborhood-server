from __future__ import annotations

import json
from pathlib import Path

import yaml

from companion.models import Envelope, JobSubmission, PlayerContext
from companion.provider import CompiledIntent, _normalize_structured_content
from companion.routing import compiled_route, route
from companion.skills import load_skills
from companion.storage import JobStore
from companion.templates import match_template


ROOT = Path(__file__).resolve().parents[1]


def test_protocol_envelope_schema_and_model_agree() -> None:
    schema = json.loads((ROOT / "protocol/envelope.schema.json").read_text())
    envelope = Envelope(type="heartbeat")
    assert envelope.protocol == schema["properties"]["protocol"]["const"]
    assert envelope.type in schema["properties"]["type"]["enum"]
    tools = json.loads((ROOT / "protocol/tools.schema.json").read_text())
    names = {tool["name"] for tool in tools["tools"]}
    assert {"set_time", "undo_last", "finish_wall", "give_looked_item"} <= names


def test_release_gates_meet_product_contract() -> None:
    gates = yaml.safe_load((ROOT / "evals/release-gates.yaml").read_text())
    scorecard = gates["scorecard"]
    assert scorecard["routing_accuracy_min"] >= 0.95
    assert scorecard["deterministic_e2e_success_min"] >= 0.98
    assert scorecard["model_e2e_success_min"] >= 0.90
    assert scorecard["safety_success_min"] == 1.0
    assert gates["latency_ms"]["tier_s_case_max"] <= 500


def test_job_submission_rejects_empty_prompt() -> None:
    player = PlayerContext(
        name="Builder",
        uuid="7ca8e2f3-27cb-4f63-9410-d62e16f72cd4",
        world="minecraft:overworld",
        x=0,
        y=64,
        z=0,
        gamemode="creative",
    )
    try:
        JobSubmission(prompt="", player=player)
    except ValueError:
        pass
    else:
        raise AssertionError("empty prompt should be rejected")


def test_tier_s_time_routes_without_model() -> None:
    for prompt, expected in (
        ("set time to day", "day"),
        ("Make it nighttime!", "night"),
        ("please change the time to noon", "noon"),
    ):
        decision = route(prompt, "job-1")
        assert decision.tier == "S"
        assert decision.action is not None
        assert decision.action.tool == "set_time"
        assert decision.action.arguments == {"time": expected}


def test_kid_friendly_core_aliases() -> None:
    give = route("give me three dirt blocks", "job-give")
    assert give.action is not None
    assert give.action.arguments == {"material": "dirt", "amount": 3}

    summon = route("spawn 3 chickens here", "job-mob")
    assert summon.tier == "A"
    assert summon.action is not None
    assert summon.action.arguments == {"entity": "chicken", "count": 3}

    speech_typo = route("spawn tree chickens here", "job-mob-typo")
    assert speech_typo.tier == "A"
    assert speech_typo.action is not None
    assert speech_typo.action.arguments == {"entity": "chicken", "count": 3}

    undo = route("undo that", "job-undo")
    assert undo.tier == "S"
    assert undo.action is not None
    assert undo.action.tool == "undo_last"

    wall = route("finish this wall in front of me 20 blocks high", "job-wall")
    assert wall.tier == "A"
    assert wall.action is not None
    assert wall.action.tool == "finish_wall"
    assert wall.action.arguments == {"height": 20}


def test_sqlite_store_is_durable(tmp_path: Path) -> None:
    db = tmp_path / "companion.sqlite3"
    store = JobStore(db)
    store.create_job(
        job_id="job-1",
        trace_id="trace-1",
        player_uuid="player-1",
        prompt="set time to day",
    )
    store.set_route("job-1", "grammar.set_time")
    store.add_action(
        action_id="action-1",
        job_id="job-1",
        idempotency_key="key-1",
        tool="set_time",
        arguments={"time": "day"},
    )
    correlation = store.action_correlation("action-1")
    assert correlation is not None
    assert correlation[:2] == ("job-1", "trace-1")
    store.complete_action("action-1", {"ok": True})
    store.complete_job("job-1", ok=True, message="Made it daytime.")
    store.record_feedback(player_uuid="player-1", rating="good")
    assert store.counts() == {"jobs": 1, "actions": 1}
    assert store.feedback_count() == 1
    assert JobStore(db).counts() == {"jobs": 1, "actions": 1}


def test_model_output_is_revalidated_before_execution() -> None:
    safe = compiled_route(
        CompiledIntent(
            kind="action",
            tool="summon_entity",
            arguments={"entity": "chicken", "count": 3},
        ),
        "job-safe",
    )
    assert safe.action is not None
    assert safe.action.risk == "bounded"

    # Count over the hard cap — still rejected after summon loosen.
    invalid = compiled_route(
        CompiledIntent(
            kind="action",
            tool="summon_entity",
            arguments={"entity": "chicken", "count": 21},
        ),
        "job-unsafe",
    )
    assert invalid.action is None
    assert invalid.route == "model.invalid"


def test_every_enabled_skill_has_evals() -> None:
    skills = load_skills(ROOT / "skills")
    assert set(skills) == {"neighborhood.core"}
    assert len(skills["neighborhood.core"].evals) >= 5


def test_gemma_fenced_action_is_normalized_then_validated() -> None:
    raw = '```json\n{"action":"set_time","arguments":{"time":"day"},"message":""}\n```'
    normalized = _normalize_structured_content(raw)
    intent = CompiledIntent.model_validate(normalized)
    assert intent.kind == "action"
    assert intent.tool == "set_time"


def test_high_confidence_template_ranker_skips_model() -> None:
    match = match_template("please build me a small chicken coop")
    assert match is not None
    assert match.template_id == "chicken_coop_small"
    decision = route("build me a small chicken coop", "job-template")
    assert decision.tier == "A"
    assert decision.action is not None
    assert decision.action.tool == "paste_template"


def test_mega_cathedral_routes_near_player_paste() -> None:
    decision = route("build a gothic cathedral", "job-cathedral")
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "gothic_cathedral"
    assert decision.action.arguments.get("clear_site") is True


def test_clear_everything_in_the_way_sets_clear_site() -> None:
    from companion.routing import (
        CLEAR_ASK_MESSAGE,
        extract_forward_blocks,
        is_clear_ask_message,
        wants_clear_site,
    )

    assert wants_clear_site(
        "build a gothic cathedral and clear everything in the way"
    )
    assert wants_clear_site("make a spruce mansion and flatten the ground")
    assert not wants_clear_site("build a gothic cathedral")
    assert extract_forward_blocks("build a coop 20 blocks in front of me") == 20
    assert is_clear_ask_message(CLEAR_ASK_MESSAGE)

    decision = route(
        "build a gothic cathedral and clear everything in the way",
        "job-cathedral-clear",
    )
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments == {
        "template_id": "gothic_cathedral",
        "clear_site": True,
    }


def test_forward_blocks_parsed_into_paste_args() -> None:
    decision = route(
        "build a gothic cathedral 20 blocks in front of me",
        "job-cathedral-forward",
    )
    assert decision.action is not None
    assert decision.action.arguments["template_id"] == "gothic_cathedral"
    assert decision.action.arguments["forward_blocks"] == 20
    assert decision.action.arguments.get("clear_site") is True


def test_clear_ask_affirm_retries_with_clear_site() -> None:
    from companion.session import PlayerSession, resolve_followup

    session = PlayerSession()
    session.set_pending(
        original_prompt="build a gothic cathedral",
        question="I'll need to clear some ground there first — want me to?",
        kind="clear_site",
        slots={
            "default_tool": "paste_template",
            "default_arguments": {"template_id": "gothic_cathedral"},
        },
    )
    decision = resolve_followup(
        prompt="yes", session=session, job_id="job-clear-yes"
    )
    assert decision is not None
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments == {
        "template_id": "gothic_cathedral",
        "clear_site": True,
    }


def test_curated_paste_auto_clears_site() -> None:
    """Saying build X opts into clear — no chat “yes” loop."""
    decision = route("build me a small chicken coop", "job-coop-clear")
    assert decision.action is not None
    assert decision.action.arguments == {
        "template_id": "chicken_coop_small",
        "clear_site": True,
    }


def test_kid_voice_catalog_aliases_resolve() -> None:
    """Natural kid phrases should hit the right template without model help."""
    cases = [
        ("little castle", "castle_small_keep"),
        ("my castle", "castle_small_keep"),
        ("house for my chickens", "chicken_coop_small"),
        ("little home for my chickens", "chicken_coop_small"),
        ("place for chicks", "chicken_coop_small"),
        ("bee house", "bee_apiary_small"),
        ("house for bees", "bee_apiary_small"),
        ("little house", "house_cottage_small"),
        ("home", "house_cottage_small"),
        ("bridge over there", "bridge_oak_short"),
        ("wood wall", "wooden_palisade"),
        ("furnaces", "smelter_array"),
        ("bunny house", "rabbit_hutch_small"),
        ("christmas tree", "tree_spruce_pine"),
        ("wishing well", "well_village"),
        ("large garden", "garden_plot"),
        ("veggie garden", "garden_plot"),
        ("big farm", "wheat_farm_small"),
        ("crop farm", "wheat_farm_small"),
        ("greenhouse", "greenhouse_small"),
    ]
    for prompt, expected in cases:
        # Alias ranking covers the full curation set; live auto-paste only
        # considers the gold subset.
        match = match_template(prompt, gold_only=False)
        assert match is not None, prompt
        assert match.template_id == expected, (prompt, match.template_id)

