#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.16.0",
# ],
# ///
"""Thin Cursor MCP adapter over agent.tools — registers tools from tool_registry."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mcp.server.fastmcp import FastMCP

from agent import tools as T
from agent.executor import execute_tool_deterministic
from agent.tool_registry import (
    TOOL_DEFINITIONS,
    TOOL_DEFINITIONS_BY_NAME,
    validate_registry,
)

mcp = FastMCP("neighborhood-minecraft-builder")


def _text(result: T.ToolResult) -> str:
    if not result.ok:
        return result.summary()
    body = result.output or result.summary()
    if result.deterministic_signature:
        body = (
            f"{body}\n[sig={result.deterministic_signature[:12]} "
            f"{result.execution_metadata.get('policy_path', 'typed')}]"
        )
    return body


def _invoke(tool_name: str, args: dict[str, Any]) -> str:
    result = execute_tool_deterministic(tool_name, args, dry_run=False)
    return _text(result)


@mcp.tool()
def call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    """Generic MCP dispatch for any registered tool by name."""

    args = arguments or {}
    if tool_name not in TOOL_DEFINITIONS_BY_NAME:
        return f"[call_tool] ERROR: unknown tool {tool_name!r}"
    return _invoke(tool_name, args)


def _register(defn: Any) -> None:
    @mcp.tool(name=defn.name, description=defn.description)
    def _handler(**kwargs: Any) -> str:
        return _invoke(defn.name, kwargs)


validate_registry()
for _defn in TOOL_DEFINITIONS:
    if _defn.mcp:
        _register(_defn)


if __name__ == "__main__":
    mcp.run()
