"""Keyword matcher: basics must not map from Ultimate … Survival House titles."""

from __future__ import annotations

from scripts.schem_pipeline.taxonomy import (
    BASIC_STRUCTURE_INTENTS,
    is_survival_base_title,
    match_intent,
)


def test_survival_base_title_detector() -> None:
    assert is_survival_base_title("Fantasy Windmill Survival House")
    assert is_survival_base_title("Ultimate Medieval Watchtower Survival Base")
    assert is_survival_base_title("Ultimate Super Smelter Workshop Survival Base")
    assert is_survival_base_title("Ultimate Lighthouse Keeper Survival Base")
    assert not is_survival_base_title("Small Windmill")
    assert not is_survival_base_title("Village Well")
    assert not is_survival_base_title("Chicken Coop")


def test_basics_reject_ultimate_survival_house() -> None:
    cases = [
        ("Fantasy Windmill Survival House", "windmill_small"),
        ("Ultimate Medieval Watchtower Survival Base", "watchtower_tall"),
        ("Ultimate Lighthouse Keeper Survival Base", "lighthouse_short"),
        ("Ultimate Super Smelter Workshop Survival Base", "workshop_small"),
        ("Ultimate Chicken Coop Survival House", "chicken_coop_small"),
        ("Village Well Survival Base", "well_village"),
        ("Market Stall Survival House", "market_stall"),
        ("Ultimate Log Cabin Survival House", "cabin_log"),
    ]
    for title, intent in cases:
        assert intent in BASIC_STRUCTURE_INTENTS
        assert (
            match_intent(title=title, allowed_intents={intent}) is None
        ), f"should reject {title!r} → {intent}"


def test_honest_basic_titles_still_match() -> None:
    assert match_intent(title="Small Windmill").intent_id == "windmill_small"
    assert match_intent(title="Medieval Watchtower").intent_id == "watchtower_tall"
    assert match_intent(title="Short Lighthouse").intent_id == "lighthouse_short"
    assert match_intent(title="Carpenter Workshop").intent_id == "workshop_small"
    assert match_intent(title="Chicken Coop").intent_id == "chicken_coop_small"
    assert match_intent(title="Village Well").intent_id == "well_village"


def test_landmarks_may_accept_survival_showpieces() -> None:
    m = match_intent(title="Grand Medieval Tavern Inn")
    assert m is not None
    assert m.intent_id == "tavern_small"
    m = match_intent(title="Ultimate Enchanted Wizard Tower Survival Base")
    assert m is not None
    assert m.intent_id == "wizard_tower"
    m = match_intent(title="Cozy Cottage Survival House")
    assert m is not None
    assert m.intent_id == "house_cottage_small"
