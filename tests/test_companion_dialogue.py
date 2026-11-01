from __future__ import annotations

import pytest

from companion.compound import route_compound, split_compound_prompt
from companion.routing import route
from companion.session import PlayerSession, resolve_followup, resolve_revise


def test_compound_split_time_and_weather() -> None:
    parts = split_compound_prompt("make it daytime and clear the weather")
    assert parts == ["make it daytime", "clear the weather"]
    plan = route_compound("make it daytime and clear the weather", "job-1")
    assert plan is not None
    assert len(plan) == 2
    assert plan[0].action is not None and plan[0].action.tool == "set_time"
    assert plan[1].action is not None and plan[1].action.tool == "set_weather"


def test_compound_then_give() -> None:
    plan = route_compound(
        "make it daytime then give me three dirt blocks", "job-2"
    )
    assert plan is not None
    assert [item.action.tool for item in plan if item.action] == [
        "set_time",
        "give_item",
    ]


def test_vague_build_clarifies() -> None:
    decision = route("build me a house", "job-3")
    assert decision.action is None
    assert decision.route == "grammar.clarify_build"
    assert decision.pending_kind == "template"


def test_vague_build_not_overridden_by_session_history() -> None:
    """Live dialogue.clarify_build: leftover session must not paste cottage."""
    session = PlayerSession()
    session.remember_player("build me a cottage")
    session.remember_action(
        tool="paste_template",
        arguments={"template_id": "cottage_medium"},
        message="Built your Medium cottage",
    )
    session.set_pending(
        original_prompt="build me a place",
        question="What kind of place?",
        kind="template",
        slots={
            "default_tool": "paste_template",
            "default_arguments": {"template_id": "cottage_medium"},
        },
    )
    decision = resolve_followup(
        prompt="build me a house", session=session, job_id="job-clarify-guard"
    )
    assert decision is None


def test_complex_coop_phrase_routes_to_chicken_coop() -> None:
    decision = route(
        "could you please put a little home for my chickens near me?",
        "job-coop-phrase",
    )
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "chicken_coop_small"


def test_market_stall_is_gold_paste() -> None:
    decision = route("build me a market stall", "job-market")
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "market_stall"


@pytest.mark.parametrize(
    "prompt",
    [
        "market stall",
        "markket stall",
        "market",
        "shop stall",
        "build a market stall",
        "can i get a market stall",
    ],
)
def test_market_stall_semantics_not_house(prompt: str) -> None:
    """Market / stall phrasing must never paste a default cottage."""
    decision = route(prompt, f"job-market-{prompt}")
    assert decision.action is not None, (prompt, decision.route, decision.message)
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "market_stall"


def test_build_a_house_still_clarifies() -> None:
    decision = route("build a house", "job-house-clarify")
    assert decision.action is None
    assert decision.route == "grammar.clarify_build"


def test_want_give_clarifies_amount() -> None:
    decision = route("can i have dirt", "job-4")
    assert decision.action is None
    assert decision.route == "grammar.clarify_give"
    assert decision.pending_slots == {"material": "dirt"}


def test_gaze_give_looked_item_phrases() -> None:
    for prompt in (
        "give me these blocks",
        "give me that block",
        "give me some of these",
        "can I have these blocks",
        "can i get those",
        "i want this block",
        "gimme these",
        "please give me those blocks",
        "give me a stack of these",
    ):
        decision = route(prompt, f"job-gaze-{prompt}")
        assert decision.tier == "S", prompt
        assert decision.route == "grammar.give_looked_item", prompt
        assert decision.action is not None, prompt
        assert decision.action.tool == "give_looked_item", prompt
        assert decision.action.arguments == {}, prompt

    counted = route("give me 16 of these", "job-gaze-16")
    assert counted.action is not None
    assert counted.action.tool == "give_looked_item"
    assert counted.action.arguments == {"amount": 16}

    one = route("give me one of those blocks", "job-gaze-one")
    assert one.action is not None
    assert one.action.arguments == {"amount": 1}


def test_named_give_not_stolen_by_gaze_route() -> None:
    named = route("give me a diamond sword", "job-named-sword")
    assert named.action is not None
    assert named.action.tool == "give_item"
    assert named.action.arguments["material"] == "diamond_sword"

    dirt = route("give me three dirt blocks", "job-named-dirt")
    assert dirt.action is not None
    assert dirt.action.tool == "give_item"
    assert dirt.action.arguments == {"material": "dirt", "amount": 3}


def test_followup_amount_resolves_give() -> None:
    session = PlayerSession()
    session.set_pending(
        original_prompt="can i have dirt",
        question="How many dirt?",
        kind="give",
        slots={"material": "dirt"},
    )
    decision = resolve_followup(prompt="16", session=session, job_id="job-5")
    assert decision is not None
    assert decision.action is not None
    assert decision.action.tool == "give_item"
    assert decision.action.arguments == {"material": "dirt", "amount": 16}


def test_followup_template_resolves_from_pending() -> None:
    session = PlayerSession()
    session.set_pending(
        original_prompt="build me a house",
        question="What kind of place?",
        kind="template",
        slots={
            "default_tool": "paste_template",
            "default_arguments": {"template_id": "cottage_medium"},
        },
    )
    decision = resolve_followup(
        prompt="small chicken coop", session=session, job_id="job-6"
    )
    assert decision is not None
    assert decision.action is not None
    assert decision.action.tool == "paste_template"
    assert decision.action.arguments["template_id"] == "chicken_coop_small"


def test_followup_yes_uses_default_template() -> None:
    session = PlayerSession()
    session.set_pending(
        original_prompt="build me a house",
        question="What kind of place?",
        kind="template",
        slots={
            "default_tool": "paste_template",
            "default_arguments": {"template_id": "cottage_medium"},
        },
    )
    decision = resolve_followup(prompt="yes", session=session, job_id="job-7")
    assert decision is not None
    assert decision.action is not None
    assert decision.action.arguments["template_id"] == "cottage_medium"


def test_finish_floor_routes_with_material() -> None:
    decision = route("finish this floor with glass", "job-floor")
    assert decision.action is not None
    assert decision.action.tool == "finish_floor"
    assert decision.action.arguments["material"] == "glass"
    assert decision.action.arguments.get("mode") == "fill"


def test_finish_floor_replace_and_clear_routes() -> None:
    replace = route("make this floor oak planks", "job-floor-r")
    assert replace.action is not None
    assert replace.action.tool == "finish_floor"
    assert replace.action.arguments == {"mode": "replace", "material": "oak_planks"}
    clear = route("clear the floor", "job-floor-c")
    assert clear.action is not None
    assert clear.action.tool == "finish_floor"
    assert clear.action.arguments == {"mode": "clear"}


@pytest.mark.parametrize(
    "prompt",
    [
        "finish the second floor",
        "build a second floor",
        "build a second floor for my castle",
        "make a second floor on my castle",
        "add a next floor",
        "build an upper story",
    ],
)
def test_upper_floor_routes_to_finish_floor_not_paste(prompt: str) -> None:
    decision = route(prompt, "job-upper")
    assert decision.action is not None
    assert decision.action.tool == "finish_floor"
    assert decision.action.arguments.get("mode") == "fill"
    assert "material" not in decision.action.arguments
    assert decision.action.arguments.get("template_id") is None


def test_never_mind_cancels_not_undo() -> None:
    decision = route("never mind", "job-cancel")
    assert decision.action is None
    assert decision.route == "grammar.cancel"
    assert "never mind" in decision.message.lower()


def test_help_menu_is_tier_s() -> None:
    for prompt in ("help", "what can you do", "commands", "help me"):
        decision = route(prompt, "job-help")
        assert decision.tier == "S"
        assert decision.action is None
        assert decision.route == "help.menu"
        assert "help builds" in decision.message.lower()
        assert "crafter" in decision.message.lower()
        assert "/builds" in decision.message.lower()


def test_help_categories_and_catalog_titles() -> None:
    builds = route("help builds", "job-help-builds")
    assert builds.route == "help.builds"
    assert "/builds" in builds.message.lower()
    assert "help farms" in builds.message.lower()

    shapes = route("help shapes", "job-help-shapes")
    assert shapes.route == "help.shapes"
    assert "platform" in shapes.message.lower()

    farms = route("help farms", "job-help-farms")
    assert farms.route == "help.farms"
    assert "garden" in farms.message.lower()

    farms2 = route("help farms 2", "job-help-farms-2")
    assert farms2.route == "help.farms"
    assert farms2.message != farms.message

    ideas = route("ideas", "job-ideas")
    assert ideas.route == "help.builds"


def test_help_me_build_does_not_steal_build_asks() -> None:
    decision = route("help me build a house", "job-help-build")
    # Must fall through to build routing — not a playbook help page.
    assert not decision.route.startswith("help.")


def test_revise_wall_taller() -> None:
    session = PlayerSession()
    session.remember_action(
        tool="finish_wall",
        arguments={"height": 8, "material": "oak_planks"},
        message="Finished your oak planks wall",
    )
    decision = resolve_revise(prompt="make it taller", session=session, job_id="job-rev")
    assert decision is not None
    assert decision.action is not None
    assert decision.action.tool == "finish_wall"
    assert decision.action.arguments["height"] == 12
    assert decision.action.arguments["material"] == "oak_planks"


def test_revise_floor_material() -> None:
    session = PlayerSession()
    session.remember_action(
        tool="finish_floor",
        arguments={"mode": "fill", "material": "glass"},
        message="Finished your glass floor",
    )
    decision = resolve_revise(prompt="use stone", session=session, job_id="job-rev-f")
    assert decision is not None
    assert decision.action is not None
    assert decision.action.tool == "finish_floor"
    assert decision.action.arguments["material"] == "stone"
    assert decision.action.arguments["mode"] == "replace"


def test_session_persistence_roundtrip(tmp_path) -> None:
    from companion.storage import JobStore
    from companion.session import SessionStore

    store = JobStore(tmp_path / "sessions.sqlite3")
    sessions = SessionStore(store)
    session = sessions.get("player-1")
    session.set_pending(
        original_prompt="can i have dirt",
        question="How many dirt?",
        kind="give",
        slots={"material": "dirt"},
    )
    session.remember_action(
        tool="finish_wall",
        arguments={"height": 8},
        message="Finished your wall",
    )
    sessions.persist("player-1")

    sessions2 = SessionStore(store)
    restored = sessions2.get("player-1")
    pending = restored.pending_alive()
    assert pending is not None
    assert pending.kind == "give"
    assert pending.slots["material"] == "dirt"
    assert restored.last_action is not None
    assert restored.last_action.tool == "finish_wall"
