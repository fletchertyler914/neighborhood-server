"""Contract tests for hybrid template ranking."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reload_catalog():
    from agent.templates import catalog as tc

    tc.reload_catalog()
    yield
    tc.reload_catalog()


@pytest.fixture(autouse=True)
def _lexical_only(monkeypatch):
    """Deterministic CI: avoid embedding index variance."""

    monkeypatch.setenv("TEMPLATE_RANKER_MODE", "hybrid")
    monkeypatch.setenv("TEMPLATE_EMBEDDING_BACKEND", "disabled")
    monkeypatch.setenv("TEMPLATE_RANKING_AUDIT", "false")


def test_resolve_chicken_coop_high_confidence():
    from agent.templates.ranking import resolve_template

    r = resolve_template("build a small chicken coop")
    assert r.selected_template_id == "chicken_coop_small"
    assert r.confidence in ("high", "medium")


def test_resolve_stone_fortress_prefers_keep():
    from agent.templates.ranking import resolve_template

    r = resolve_template("build a stone fortress", intent_family="castle")
    assert r.selected_template_id == "castle_small_keep"


def test_resolve_hen_house_legacy_exact():
    from agent.templates.ranking import resolve_template

    r = resolve_template("hen house")
    assert r.confidence == "high"
    assert r.selected_template_id == "chicken_coop_small"
    assert r.score_breakdown.get("mode") == "legacy_exact"


def test_search_templates_tool():
    from agent.tools import search_templates

    out = search_templates("pig pen")
    assert out.ok
    assert "pig_pen" in (out.output or "")


def test_catalog_has_100_plus_templates():
    from agent.templates import catalog as tc

    assert len(list(tc.iter_templates())) >= 100


def test_catalog_category_minimums():
    from collections import Counter

    from agent.templates import catalog as tc

    counts = Counter(m.category for m in tc.iter_templates())
    assert counts.get("house", 0) >= 12
    assert counts.get("farm", 0) >= 6
    assert counts.get("fortress", 0) >= 4
    assert counts.get("infrastructure", 0) >= 4
    assert counts.get("decoration", 0) >= 4


def test_ranking_deterministic_repeat():
    from agent.templates.ranking import resolve_template

    a = resolve_template("wooden bridge")
    b = resolve_template("wooden bridge")
    assert a.selected_template_id == b.selected_template_id
    assert a.confidence == b.confidence
    assert [c.template_id for c in a.top_candidates[:3]] == [
        c.template_id for c in b.top_candidates[:3]
    ]


def test_ranking_latency_budget():
    from agent.templates.ranking import resolve_template

    t0 = time.perf_counter()
    for _ in range(20):
        resolve_template("medium cottage near the farm")
    elapsed = time.perf_counter() - t0
    # 20 resolves on ~100 templates should stay well under 2s on CI hardware
    assert elapsed < 2.0, f"ranking too slow: {elapsed:.2f}s for 20 calls"


def test_ranking_audit_writes_when_enabled(tmp_path, monkeypatch):
    from agent.templates import ranking as rank_mod
    from agent.templates.ranking_audit import ranking_audit_path

    monkeypatch.setenv("NEIGHBORHOOD_REPO", str(tmp_path))
    monkeypatch.setenv("TEMPLATE_RANKING_AUDIT", "true")
    rank_mod.resolve_template("chicken coop")
    path = ranking_audit_path()
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    assert "chicken_coop" in lines[-1] or "chicken" in lines[-1]
