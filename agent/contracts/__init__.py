"""Companion v3 tool contracts — single source for core tools exposed to the LLM."""

from agent.contracts.core import (
    COMPANION_TOOLS_VERSION,
    CORE_TOOL_NAMES,
    core_definitions,
    core_openai_schemas,
    get_core_definition,
    is_core_tool,
)
from agent.contracts.types import ToolResult, ToolRisk, ToolSpec

__all__ = [
    "COMPANION_TOOLS_VERSION",
    "CORE_TOOL_NAMES",
    "ToolResult",
    "ToolRisk",
    "ToolSpec",
    "core_definitions",
    "core_openai_schemas",
    "get_core_definition",
    "is_core_tool",
]
