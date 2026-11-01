"""Unit tests for unfulfilled-request gap logging."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from companion.gaps import classify_gap_reason
from companion.storage import JobStore


def test_classify_gap_reason_skips_success_and_noise() -> None:
    assert classify_gap_reason("grammar.clarify_build", ok=True) is None
    assert classify_gap_reason("grammar.cancel", ok=False) is None
    assert classify_gap_reason("feedback", ok=False) is None
    assert classify_gap_reason("native.clear_ask", ok=False) is None
    assert classify_gap_reason("help.overview", ok=False) is None
    assert classify_gap_reason("grammar.undo", ok=False) is None
    assert classify_gap_reason("session.undo_last", ok=False) is None


def test_classify_gap_reason_codes() -> None:
    assert classify_gap_reason("grammar.clarify_template", ok=False) == "clarify"
    assert classify_gap_reason("model.clarify", ok=False) == "clarify"
    assert classify_gap_reason("unresolved", ok=False) == "unresolved"
    assert classify_gap_reason("model.unavailable", ok=False) == "unresolved"
    assert classify_gap_reason("policy.refuse_dig", ok=False) == "refuse"
    assert classify_gap_reason("grammar.refuse_place_budget", ok=False) == "refuse"
    assert classify_gap_reason("compound.unsupported", ok=False) == "refuse"
    assert classify_gap_reason("ops.ingest.fail", ok=False) == "ingest"
    assert classify_gap_reason("pattern.place_wall", ok=False) == "failed"
    assert (
        classify_gap_reason("pattern.paste_template", ok=False, explicit="refuse")
        == "refuse"
    )
    assert classify_gap_reason("anything", ok=False, explicit="") is None


def test_record_gap_persists_append_rows(tmp_path: Path) -> None:
    db = tmp_path / "companion.sqlite3"
    store = JobStore(db)
    store.create_job(
        job_id="job-gap-1",
        trace_id="trace-1",
        player_uuid="uuid-1",
        prompt="dig a big hole",
    )
    store.set_route("job-gap-1", "policy.refuse_dig", tier="S")
    store.record_gap(
        reason="refuse",
        message="I can't dig holes yet.",
        job_id="job-gap-1",
        player_name="firecrab93",
        candidates=[],
    )
    store.record_gap(
        reason="clarify",
        message="Did you mean Cottage?",
        job_id="job-gap-2",
        player_uuid="uuid-2",
        player_name="kid",
        prompt="build me a house",
        route="grammar.clarify_build",
        tier="S",
        candidates=["Cottage", "Chicken coop", "Market stall"],
    )
    assert store.gap_count() == 2
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT reason, player_name, prompt, route, candidates_json "
        "FROM request_gaps ORDER BY id"
    ).fetchall()
    assert rows[0]["reason"] == "refuse"
    assert rows[0]["player_name"] == "firecrab93"
    assert rows[0]["prompt"] == "dig a big hole"
    assert rows[0]["route"] == "policy.refuse_dig"
    assert rows[1]["reason"] == "clarify"
    assert json.loads(rows[1]["candidates_json"]) == [
        "Cottage",
        "Chicken coop",
        "Market stall",
    ]


def test_successful_job_not_recorded_as_gap(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "ok.sqlite3")
    store.create_job(
        job_id="job-ok",
        trace_id="t",
        player_uuid="u",
        prompt="make it daytime",
    )
    store.set_route("job-ok", "grammar.set_time", tier="S")
    store.complete_job("job-ok", ok=True, message="Made it daytime.")
    assert classify_gap_reason("grammar.set_time", ok=True) is None
    assert store.gap_count() == 0
