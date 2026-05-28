"""Unit tests for training data extraction from feedback ratings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("NEIGHBORHOOD_REPO", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    import agent.feedback as fb

    fb._audit_loaded = False
    fb._last_job_by_player.clear()
    yield tmp_path
    fb._audit_loaded = False
    fb._last_job_by_player.clear()


def test_join_feedback_links_ratings_to_audit_entries(repo: Path):
    audit_path = repo / "data" / "agent-audit.log"
    fb_path = repo / "data" / "agent-feedback.jsonl"

    _write_jsonl(
        audit_path,
        [
            {
                "job_id": "job-good",
                "player": "p1",
                "uuid": "u",
                "prompt": "build a castle",
                "status": "done",
                "tool_calls": [
                    {
                        "name": "build_castle_at_player",
                        "arguments": {"player": "p1", "size": 11},
                    }
                ],
                "message": "Built a castle.",
                "model": "qwen2.5",
            },
            {
                "job_id": "job-bad",
                "player": "p1",
                "uuid": "u",
                "prompt": "build a castle",
                "status": "done",
                "tool_calls": [
                    {
                        "name": "build_cylinder",
                        "arguments": {"radius": 10, "height": 20, "hollow": False},
                    }
                ],
                "message": "Built a cylinder.",
                "model": "qwen2.5",
            },
        ],
    )
    _write_jsonl(
        fb_path,
        [
            {
                "feedback_id": "fb1",
                "job_id": "job-good",
                "timestamp": "t",
                "player": "p1",
                "rating": "good",
                "note": "",
                "prompt": "build a castle",
                "tool_names": ["build_castle_at_player"],
                "model": "qwen2.5",
                "source": "chat",
            },
            {
                "feedback_id": "fb2",
                "job_id": "job-bad",
                "timestamp": "t",
                "player": "p1",
                "rating": "bad",
                "note": "walls were solid",
                "prompt": "build a castle",
                "tool_names": ["build_cylinder"],
                "model": "qwen2.5",
                "source": "chat",
            },
        ],
    )

    from agent.training.feedback import (
        build_dpo_pairs,
        build_sft,
        join_feedback,
    )

    rows = list(join_feedback(fb_path, audit_path))
    assert {r.rating for r in rows} == {"good", "bad"}
    assert {r.audit["job_id"] for r in rows} == {"job-good", "job-bad"}

    sft = build_sft(rows, system_prompt="SYS")
    # Only the 'good' row becomes an SFT example by default.
    assert len(sft) == 1
    ex = sft[0]
    assert ex["messages"][0]["role"] == "system"
    assert ex["messages"][0]["content"] == "SYS"
    assert ex["messages"][1]["role"] == "user"
    assert ex["messages"][1]["content"] == "build a castle"
    asst = ex["messages"][2]
    assert asst["role"] == "assistant"
    assert asst["tool_calls"][0]["function"]["name"] == "build_castle_at_player"

    sft_with_neg = build_sft(rows, system_prompt="SYS", include_bad_as_negative=True)
    assert len(sft_with_neg) == 2
    assert any(e["meta"].get("negative") for e in sft_with_neg)

    dpo = build_dpo_pairs(rows)
    assert len(dpo) == 1
    pair = dpo[0]
    assert pair["prompt"] == "build a castle"
    assert pair["chosen"][0]["function"]["name"] == "build_castle_at_player"
    assert pair["rejected"][0]["function"]["name"] == "build_cylinder"


def test_sft_meta_includes_routing_fields(repo: Path):
    audit_path = repo / "data" / "agent-audit.log"
    fb_path = repo / "data" / "agent-feedback.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "job_id": "job-template",
                "player": "p1",
                "uuid": "u",
                "prompt": "make a chicken coop",
                "status": "done",
                "tool_calls": [
                    {
                        "name": "paste_template_at_player",
                        "arguments": {
                            "player": "p1",
                            "template_id": "chicken_coop_small",
                        },
                    }
                ],
                "routing": {
                    "intent_family": "farm_pen",
                    "selected_tool": "paste_template_at_player",
                    "selected_template_id": "chicken_coop_small",
                    "rewrite_applied": True,
                    "original_tool": "build_house",
                },
            }
        ],
    )
    _write_jsonl(
        fb_path,
        [
            {
                "feedback_id": "fb-t",
                "job_id": "job-template",
                "timestamp": "t",
                "player": "p1",
                "rating": "good",
                "prompt": "make a chicken coop",
                "tool_names": ["paste_template_at_player"],
                "source": "chat",
            }
        ],
    )
    from agent.training.feedback import build_sft, join_feedback

    rows = list(join_feedback(fb_path, audit_path))
    ex = build_sft(rows)[0]
    assert ex["meta"]["intent_family"] == "farm_pen"
    assert ex["meta"]["selected_template_id"] == "chicken_coop_small"
    assert ex["meta"]["rewrite_applied"] is True
    assert ex["meta"]["original_tool"] == "build_house"


def test_join_feedback_drops_entries_without_tool_calls(repo: Path):
    audit_path = repo / "data" / "agent-audit.log"
    fb_path = repo / "data" / "agent-feedback.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "job_id": "j",
                "player": "p",
                "uuid": "u",
                "prompt": "hi",
                "status": "done",
                "tool_calls": [],
                "message": "hi",
                "model": "",
            }
        ],
    )
    _write_jsonl(
        fb_path,
        [
            {
                "feedback_id": "fb",
                "job_id": "j",
                "timestamp": "t",
                "player": "p",
                "rating": "good",
                "note": "",
                "prompt": "hi",
                "tool_names": [],
                "model": "",
                "source": "chat",
            }
        ],
    )

    from agent.training.feedback import join_feedback

    assert list(join_feedback(fb_path, audit_path)) == []
