"""Gold corpus catalog invariants."""

from __future__ import annotations

import sys
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


def test_gold_corpus_size_at_least_fifty():
    from agent.templates import catalog as tc

    raw = tc.load_catalog()
    assert len(raw.get("templates") or []) >= 50


def test_gold_entries_have_fallback_and_provenance():
    from agent.templates import catalog as tc

    for meta in tc.iter_templates():
        assert meta.fallback or meta.fallback_steps, f"{meta.id} missing fallback"
        assert meta.source_id
        assert meta.license


def test_new_template_aliases_resolve():
    from agent.templates import catalog as tc

    assert tc.resolve_template_id("watchtower") == "watchtower_tall"
    assert tc.resolve_template_id("tavern") == "tavern_small"
    assert tc.resolve_template_id("wheat farm") == "wheat_farm_small"
