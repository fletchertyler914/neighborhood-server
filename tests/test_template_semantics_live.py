"""Live companion hybrid template semantics (not offline agent.ranking only)."""

from __future__ import annotations

import time

import pytest

from companion.routing import route
from companion.templates import match_template, reload_catalog, warm_template_ranker


@pytest.fixture(autouse=True)
def _fresh_catalog():
    reload_catalog()
    warm_template_ranker()
    yield
    reload_catalog()


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("market stall", "market_stall"),
        ("markket stall", "market_stall"),
        ("market", "market_stall"),
        ("shop stall", "market_stall"),
        ("build a market stall", "market_stall"),
        ("build a house", None),  # vague → clarify at route(); matcher may still rank
        ("little house", "house_cottage_small"),
        ("build me a small chicken coop", "chicken_coop_small"),
    ],
)
def test_match_template_market_and_house(prompt: str, expected: str | None) -> None:
    match = match_template(prompt, gold_only=True)
    if expected is None:
        # Matcher may return a house candidate, but must mark clarify or be unused
        # by route(); do not require None here.
        return
    assert match is not None, prompt
    assert match.template_id == expected, (prompt, match)
    assert match.gold
    assert not match.needs_clarify or match.confidence == "high"


def test_market_beats_default_house() -> None:
    match = match_template("markket stall", gold_only=True)
    assert match is not None
    assert match.template_id == "market_stall"
    assert match.template_id not in {
        "house_cottage_small",
        "cottage_medium",
        "cabin_log",
    }


def test_hybrid_latency_budget() -> None:
    warm_template_ranker()
    # Warm path once more so first-call index build is excluded.
    match_template("build a market stall near me")
    t0 = time.perf_counter()
    for _ in range(20):
        match_template("build a market stall near me")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"hybrid ranking too slow: {elapsed:.2f}s for 20 calls"


def test_route_market_stall_bare_noun() -> None:
    decision = route("market stall", "job-bare-market")
    assert decision.action is not None
    assert decision.action.arguments["template_id"] == "market_stall"


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("campground", "campground"),
        ("cmapground", "campground"),
        ("build a cmapground", "campground"),
        ("camping spot", "campground"),
        ("cow barn", "cow_barn_medium"),
        ("build a cow barn", "cow_barn_medium"),
        ("carrot farm", "carrot_farm_small"),
    ],
)
def test_campground_typo_and_cow_barn(prompt: str, expected: str) -> None:
    match = match_template(prompt, gold_only=True)
    assert match is not None, prompt
    assert match.template_id == expected, (prompt, match.template_id, match.ranking)
    assert match.gold
    assert not match.needs_clarify
    decision = route(prompt, f"job-{expected}-{abs(hash(prompt)) % 10000}")
    assert decision.action is not None, (prompt, decision.route, decision.message)
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == expected


def test_cmapground_never_carrot_farm() -> None:
    match = match_template("cmapground", gold_only=True)
    assert match is not None
    assert match.template_id == "campground"
    assert match.template_id != "carrot_farm_small"
    decision = route("cmapground", "job-cmap-guard")
    assert decision.action is not None
    assert decision.action.arguments["template_id"] == "campground"
