"""Shared Minecraft tool implementations for MCP and in-game orchestrator."""

from __future__ import annotations

import json
from typing import Any

import agent.tools as tools_pkg
from agent.tool_registry import build_dispatch, build_openai_schemas, validate_registry
from agent.tools import _monolith as _m

for _name in dir(_m):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_m, _name)

ToolResult = _m.ToolResult
_dispatch_entry = _m._dispatch_entry
_err = _m._err

_raw_dispatch = build_dispatch(tools_pkg)
TOOL_DISPATCH: dict[str, Any] = {
    name: _dispatch_entry(fn) for name, fn in _raw_dispatch.items()
}


def _execute_tool_raw(name: str, arguments: dict[str, Any], dry_run: bool = False) -> ToolResult:
    """Low-level dispatch without schema validation or signatures."""

    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return _err(name, ValueError(f"unknown tool: {name}"))
    if dry_run:
        return ToolResult(
            ok=True,
            tool=name,
            output=f"dry-run: would call {name} with {json.dumps(arguments)}",
            commands=[],
        )
    return fn(**arguments)


def execute_tool(name: str, arguments: dict[str, Any], dry_run: bool = False) -> ToolResult:
    """Dispatch a tool by name. Used by orchestrator and tests."""
    from agent.executor import execute_tool_deterministic

    return execute_tool_deterministic(name, arguments, dry_run=dry_run)


TOOL_SCHEMAS = build_openai_schemas(orchestrator_only=True)

validate_registry()
