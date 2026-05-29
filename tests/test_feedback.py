"""Unit tests for the agent feedback collection system."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEIGHBORHOOD_REPO", str(tmp_path))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    # Force the feedback module to re-read state from this dir.
    import agent.feedback as fb

    fb._audit_loaded = False
    fb._last_job_by_player.clear()
    yield tmp_path
    fb._audit_loaded = False
    fb._last_job_by_player.clear()


def _write_audit(repo: Path, entries: list[dict]) -> None:
    path = repo / "data" / "agent-audit.log"
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_parse_rating_prompt_recognizes_good_and_bad():
    from agent.feedback import parse_rating_prompt

    assert parse_rating_prompt("good").rating == "good"
    assert parse_rating_prompt("good job").rating == "good"
    assert parse_rating_prompt("nice").rating == "good"
    assert parse_rating_prompt("great job").rating == "good"

    bad = parse_rating_prompt("bad the walls were solid")
    assert bad is not None
    assert bad.rating == "bad"
    assert bad.note == "the walls were solid"

    assert parse_rating_prompt("rate bad - door was missing").rating == "bad"
    assert parse_rating_prompt("build a castle") is None


def test_record_feedback_resolves_last_job_from_audit(isolated_data_dir):
    _write_audit(
        isolated_data_dir,
        [
            {
                "job_id": "job-1",
                "timestamp": "t1",
                "player": "JavaTester",
                "uuid": "uu1",
                "prompt": "build a castle",
                "status": "done",
                "model": "qwen2.5",
                "steps": 1,
                "tool_calls": [{"name": "build_cylinder", "arguments": {}}],
                "message": "done",
                "dry_run": False,
            }
        ],
    )

    from agent.feedback import record_feedback, feedback_log_path

    entry = record_feedback(
        player="JavaTester",
        rating="bad",
        note="walls were solid",
        source="chat",
    )
    assert entry.job_id == "job-1"
    assert entry.rating == "bad"
    assert entry.note == "walls were solid"
    assert entry.prompt == "build a castle"
    assert entry.tool_names == ["build_cylinder"]

    lines = feedback_log_path().read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["job_id"] == "job-1"
    assert written["rating"] == "bad"
    assert written["note"] == "walls were solid"


def test_record_feedback_copies_routing_from_audit(isolated_data_dir):
    _write_audit(
        isolated_data_dir,
        [
            {
                "job_id": "job-routed",
                "player": "JavaTester",
                "uuid": "uu",
                "prompt": "make a chicken coop",
                "status": "done",
                "tool_calls": [
                    {
                        "name": "paste_template_at_player",
                        "arguments": {"template_id": "chicken_coop_small"},
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
    from agent.feedback import feedback_log_path, record_feedback

    entry = record_feedback(player="JavaTester", rating="good")
    assert entry.routing["intent_family"] == "farm_pen"
    assert entry.routing["selected_template_id"] == "chicken_coop_small"
    written = json.loads(feedback_log_path().read_text(encoding="utf-8").strip())
    assert written["routing"]["rewrite_applied"] is True


def test_record_feedback_uses_in_memory_last_job_when_no_audit(isolated_data_dir):
    from agent.feedback import record_feedback, remember_last_job

    remember_last_job("JavaTester", "live-job-xyz")
    entry = record_feedback(player="JavaTester", rating="good")
    assert entry.job_id == "live-job-xyz"
    assert entry.tool_names == []  # no audit entry for this job
    assert entry.prompt == ""


def test_record_feedback_explicit_job_id_wins(isolated_data_dir):
    _write_audit(
        isolated_data_dir,
        [
            {
                "job_id": "other-job",
                "player": "JavaTester",
                "uuid": "uu",
                "prompt": "older",
                "status": "done",
                "tool_calls": [{"name": "say", "arguments": {}}],
                "message": "",
            }
        ],
    )

    from agent.feedback import record_feedback

    entry = record_feedback(
        player="JavaTester",
        rating="good",
        job_id="other-job",
    )
    assert entry.job_id == "other-job"
    assert entry.tool_names == ["say"]


def test_record_feedback_raises_without_any_job(isolated_data_dir):
    from agent.feedback import record_feedback

    with pytest.raises(LookupError):
        record_feedback(player="never-played", rating="good")


def test_handle_rating_job_returns_done_with_no_tool_calls(isolated_data_dir):
    _write_audit(
        isolated_data_dir,
        [
            {
                "job_id": "job-A",
                "player": "JavaTester",
                "uuid": "uu",
                "prompt": "build a castle",
                "status": "done",
                "tool_calls": [{"name": "build_cylinder", "arguments": {}}],
                "message": "done",
            }
        ],
    )

    from agent.feedback import parse_rating_prompt
    from agent.job import JobRequest
    from agent.orchestrator import _handle_rating_job, JobStatus

    req = JobRequest(
        player="JavaTester",
        uuid="uu",
        prompt="bad walls were solid",
        x=0,
        y=80,
        z=0,
    )
    parsed = parse_rating_prompt(req.prompt)
    assert parsed is not None and parsed.rating == "bad"
    resp = _handle_rating_job(req, parsed)
    assert resp.status == JobStatus.done
    assert resp.tool_calls == []
    assert "bad" in resp.message.lower()


def test_handle_rating_job_when_no_prior_job(isolated_data_dir):
    from agent.feedback import parse_rating_prompt
    from agent.job import JobRequest
    from agent.orchestrator import _handle_rating_job, JobStatus

    req = JobRequest(
        player="newbie",
        uuid="uu",
        prompt="good",
        x=0,
        y=80,
        z=0,
    )
    parsed = parse_rating_prompt(req.prompt)
    assert parsed is not None
    resp = _handle_rating_job(req, parsed)
    assert resp.status == JobStatus.done
    assert "nothing to rate" in resp.message.lower()


def test_audit_hydration_skips_feedback_entries(isolated_data_dir):
    _write_audit(
        isolated_data_dir,
        [
            {
                "job_id": "real-1",
                "player": "JavaTester",
                "uuid": "uu",
                "prompt": "build a wall",
                "status": "done",
                "tool_calls": [{"name": "fill_box", "arguments": {}}],
                "message": "",
            },
            {
                "job_id": "rating-1",
                "player": "JavaTester",
                "uuid": "uu",
                "prompt": "good",
                "status": "feedback",  # should be ignored
                "tool_calls": [],
                "message": "",
            },
        ],
    )

    from agent.feedback import get_last_job

    assert get_last_job("JavaTester") == "real-1"
