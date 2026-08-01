"""One execute() for evals, bake-off, thin agent, and (later) MCP."""

from __future__ import annotations

import os
from typing import Any

from agent.contracts.core import is_core_tool
from agent.contracts.types import ToolResult
from agent.dispatch.protocol import DispatchTransport

# v1: RCON via existing tool implementations.
_TRANSPORT = DispatchTransport(
    os.environ.get("AGENT_DISPATCH_TRANSPORT", DispatchTransport.rcon.value)
)


def execute(
    tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    core_only: bool = True,
) -> ToolResult:
    """Run a typed tool. Prefer this over calling agent.tools directly."""

    arguments = dict(arguments or {})
    if core_only and not is_core_tool(tool):
        return ToolResult(
            ok=False,
            tool=tool,
            output="",
            error=f"tool not in companion core set: {tool}",
        )
    if _TRANSPORT == DispatchTransport.plugin_native:
        return ToolResult(
            ok=False,
            tool=tool,
            output="",
            error="plugin_native transport not implemented yet; use AGENT_DISPATCH_TRANSPORT=rcon",
        )

    from agent import tools as T

    legacy = T.execute_tool(tool, arguments, dry_run=dry_run)
    return ToolResult.from_legacy(legacy)
