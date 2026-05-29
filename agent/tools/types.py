"""Shared tool types and limits."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

CONTAINER = os.environ.get("MC_CONTAINER", "mc-lan")
RCON_MODE = os.environ.get("RCON_MODE", "exec").lower()
MAX_BLOCKS = int(os.environ.get("MINECRAFT_MCP_MAX_BLOCKS", "200000"))
MAX_COMMANDS = int(os.environ.get("MINECRAFT_MCP_MAX_COMMANDS", "20000"))


@dataclass(frozen=True)
class Vec3:
    x: int
    y: int
    z: int


@dataclass
class ToolResult:
    ok: bool
    tool: str
    output: str
    commands: list[str] = field(default_factory=list)
    block_estimate: int = 0
    error: str | None = None
    deterministic_signature: str = ""
    execution_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "tool": self.tool,
            "output": self.output,
            "commands": self.commands,
            "block_estimate": self.block_estimate,
            "error": self.error,
        }
        if self.deterministic_signature:
            out["deterministic_signature"] = self.deterministic_signature
        if self.execution_metadata:
            out["execution_metadata"] = self.execution_metadata
        return out

    def summary(self) -> str:
        if self.error:
            return f"[{self.tool}] ERROR: {self.error}"
        return f"[{self.tool}] {self.output}"
