"""Unit tests for companion v3 contracts (no live server)."""

from __future__ import annotations

from agent.contracts import (
    COMPANION_TOOLS_VERSION,
    CORE_TOOL_NAMES,
    core_definitions,
    core_openai_schemas,
    is_core_tool,
)
from agent.skills import list_skills, load_skill, select_skill, schemas_for_skill


def test_core_tool_count():
    assert len(CORE_TOOL_NAMES) == 12
    assert COMPANION_TOOLS_VERSION.startswith("3.")


def test_core_schemas_match_definitions():
    defs = core_definitions()
    schemas = core_openai_schemas()
    assert len(defs) == len(schemas) == 12
    names = {s["function"]["name"] for s in schemas}
    assert names == set(CORE_TOOL_NAMES)


def test_is_core_tool():
    assert is_core_tool("paste_template_at_player")
    assert not is_core_tool("build_castle_at_player")


def test_skills_seeded():
    skills = list_skills()
    assert "build" in skills
    assert "admin" in skills
    assert "mobs" in skills
    assert "meta" in skills
    build = load_skill("build")
    assert "paste_template_at_player" in build.tools
    assert schemas_for_skill("admin")


def test_select_skill():
    assert select_skill("set time to day") == "admin"
    assert select_skill("summon 5 chickens") == "mobs"
    assert select_skill("build a chicken coop") == "build"
