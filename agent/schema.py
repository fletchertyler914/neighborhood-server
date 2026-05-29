"""OpenAI-compatible tool schemas for LLM orchestration.

Generated from the single source of truth in ``agent.tool_registry``.
"""

from __future__ import annotations

from agent.tool_registry import TOOLS_SCHEMA_VERSION, TOOLS_VERSION, build_openai_schemas

TOOL_SCHEMAS: list = build_openai_schemas(orchestrator_only=True)

__all__ = ["TOOL_SCHEMAS", "TOOLS_VERSION", "TOOLS_SCHEMA_VERSION"]
