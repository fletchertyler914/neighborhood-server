"""Dispatch transport protocol — RCON today, plugin-native next."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from agent.contracts.types import ToolResult


class DispatchTransport(str, Enum):
    """How tool side-effects reach Paper."""

    rcon = "rcon"
    # Future: structured tool call → NeighborhoodAgent plugin Bukkit/FAWE API.
    plugin_native = "plugin_native"


class PluginNativeProtocol(Protocol):
    """Long-term executor contract (not the v1 transport).

    The Paper plugin would expose an internal endpoint or command that accepts
    ``{tool, arguments}`` and returns a ``ToolResult``-shaped JSON payload,
    running FAWE/Bukkit as the real player (extending /agentexec).
    """

    def execute_native(self, tool: str, arguments: dict[str, Any]) -> ToolResult: ...
