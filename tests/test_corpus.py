"""Tests for corpus schema, loader, and assertions."""

from __future__ import annotations

from agent.eval.corpus_assertions import assert_corpus_expect, classify_primary_failure
from agent.eval.corpus_case import CorpusCase, CorpusExpect, ToolExpectAny, WorldProbe
from agent.eval.corpus_loader import load_corpus


def test_corpus_loads_minimum_count():
    suite = load_corpus()
    assert len(suite.cases) >= 600


def test_corpus_unique_ids():
    suite = load_corpus()
    ids = [c.id for c in suite.cases]
    assert len(ids) == len(set(ids))


def test_tool_any_match():
    expect = CorpusExpect(
        tool_any=[
            ToolExpectAny(
                name="paste_template_at_player",
                arguments_any=[{"template_id": "cabin_log"}],
            )
        ],
        world_probe=WorldProbe(kind="none"),
    )
    failures = assert_corpus_expect(
        expect,
        actual_status="done",
        actual_steps=2,
        tool_calls=[
            {
                "name": "paste_template_at_player",
                "arguments": {"player": "Steve", "template_id": "cabin_log"},
            }
        ],
        world_probe_ok=True,
        world_probe_message="ok",
    )
    assert failures == []


def test_tool_any_semantic_success_on_synonym_template():
    expect = CorpusExpect(
        tool_any=[
            ToolExpectAny(
                name="paste_template_at_player",
                arguments_any=[{"template_id": "cabin_log"}],
            )
        ],
        world_probe=WorldProbe(kind="none"),
    )
    failures = assert_corpus_expect(
        expect,
        actual_status="done",
        actual_steps=2,
        tool_calls=[
            {
                "name": "paste_template_at_player",
                "arguments": {"player": "Steve", "template_id": "house_cottage_small"},
                "result": {"ok": True, "output": "pasted template house_cottage_small at (1, 2, 3)"},
            }
        ],
        world_probe_ok=True,
        world_probe_message="ok",
    )
    assert failures == []


def test_tool_any_miss_classified():
    expect = CorpusExpect(
        tool_any=[ToolExpectAny(name="build_platform")],
        world_probe=WorldProbe(kind="none"),
    )
    failures = assert_corpus_expect(
        expect,
        actual_status="done",
        actual_steps=2,
        tool_calls=[{"name": "say", "arguments": {"message": "hi"}}],
        world_probe_ok=True,
        world_probe_message="ok",
    )
    assert classify_primary_failure(failures) == "tool_selection_miss"


def test_failed_tool_is_classified_before_world_probe_failure():
    expect = CorpusExpect(
        tool_any=[ToolExpectAny(name="build_platform")],
        world_probe=WorldProbe(kind="shape_built", shape="platform", block="quartz_block"),
    )

    failures = assert_corpus_expect(
        expect,
        actual_status="done",
        actual_steps=2,
        tool_calls=[
            {
                "name": "build_platform",
                "arguments": {"block": "quartz_block"},
                "result": {
                    "ok": False,
                    "error": "That position is not loaded",
                },
            }
        ],
        world_probe_ok=False,
        world_probe_message="tool failed; skipping world probe",
    )

    assert classify_primary_failure(failures) == "server_error"
    assert {f.kind for f in failures} == {"server_error", "world_state_wrong"}


def test_build_datasets_from_synthetic_envelope():
    from agent.training.build_datasets import build_dpo_from_envelopes, build_sft_from_envelopes

    rows = [
        {
            "ok": True,
            "prompt": "build a cabin",
            "case_id": "a",
            "trace": [{"name": "paste_template_at_player", "arguments": {"template_id": "cabin"}}],
            "job_id": "j1",
        },
        {
            "ok": False,
            "prompt": "build a cabin",
            "case_id": "b",
            "trace": [{"name": "say", "arguments": {}}],
            "job_id": "j2",
        },
    ]
    sft = build_sft_from_envelopes(rows)
    dpo = build_dpo_from_envelopes(rows)
    assert len(sft) == 1
    assert len(dpo) == 1
    assert sft[0]["messages"][0]["role"] == "user"


def test_world_verification_false_mines_negative_pair():
    from agent.training.build_datasets import build_dpo_from_envelopes, build_sft_from_envelopes

    rows = [
        {
            "ok": True,
            "prompt": "build a cabin",
            "case_id": "good",
            "trace": [{"name": "paste_template_at_player", "arguments": {"template_id": "cabin"}}],
            "job_id": "j1",
            "world_verification": {"verified_ok": True},
        },
        {
            "ok": True,
            "prompt": "build a cabin",
            "case_id": "bad-world",
            "trace": [{"name": "build_platform", "arguments": {"block": "dirt"}}],
            "job_id": "j2",
            "world_verification": {"verified_ok": False, "reason": "roof missing"},
        },
    ]

    sft = build_sft_from_envelopes(rows)
    dpo = build_dpo_from_envelopes(rows)

    assert len(sft) == 1
    assert len(dpo) == 1
    assert dpo[0]["meta"]["rejected_world_verification"]["reason"] == "roof missing"
