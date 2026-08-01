"""Core tool allowlist for companion v3 — DRY over the existing registry."""

from __future__ import annotations

from agent.contracts.types import ToolRisk, ToolSpec
from agent.tool_registry import TOOL_DEFINITIONS_BY_NAME

# Companion foundation contract version (independent of legacy TOOLS_VERSION).
COMPANION_TOOLS_VERSION = "3.0.0"

# Exact set from the ground-up plan. Nothing else is LLM-exposed until skills.
CORE_TOOL_NAMES: tuple[str, ...] = (
    "preflight",
    "list_players",
    "set_time",
    "set_weather",
    "give_item",
    "summon_entity",
    "build_platform",
    "fawe_sphere_at_player",
    "fawe_cyl_at_player",
    "paste_template_at_player",
    "list_templates",
    "run_command",
)


def is_core_tool(name: str) -> bool:
    return name in CORE_TOOL_NAMES


def get_core_definition(name: str) -> ToolSpec:
    defn = TOOL_DEFINITIONS_BY_NAME.get(name)
    if defn is None or not is_core_tool(name):
        raise KeyError(f"not a core companion tool: {name}")
    try:
        risk = ToolRisk(defn.risk)
    except ValueError:
        risk = ToolRisk.low
    return ToolSpec(
        name=defn.name,
        description=defn.description,
        parameters=defn.parameters,
        category=defn.category,
        risk=risk,
    )


def core_definitions() -> list[ToolSpec]:
    return [get_core_definition(n) for n in CORE_TOOL_NAMES]


def core_openai_schemas() -> list[dict]:
    return [spec.to_openai_schema() for spec in core_definitions()]
