"""Typed results and specs for the companion foundation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    destructive = "destructive"


class ToolSpec(BaseModel):
    """Minimal contract for a companion tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    category: str = "general"
    risk: ToolRisk = ToolRisk.low

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolResult(BaseModel):
    ok: bool
    tool: str
    output: str = ""
    commands: list[str] = Field(default_factory=list)
    block_estimate: int = 0
    error: str | None = None
    execution_metadata: dict[str, Any] = Field(default_factory=dict)

    def summary(self) -> str:
        if self.error:
            return f"[{self.tool}] ERROR: {self.error}"
        return f"[{self.tool}] {self.output}"

    def canned_chat(self) -> str:
        """One-line in-game reply — no second LLM round."""
        if not self.ok:
            return f"Failed: {self.error or self.output or 'unknown error'}"
        text = (self.output or "Done.").strip().replace("\n", " ")
        if len(text) > 180:
            text = text[:177] + "..."
        return text

    @classmethod
    def from_legacy(cls, legacy: Any) -> ToolResult:
        """Adapt agent.tools.ToolResult dataclass."""
        if isinstance(legacy, cls):
            return legacy
        return cls(
            ok=bool(getattr(legacy, "ok", False)),
            tool=str(getattr(legacy, "tool", "")),
            output=str(getattr(legacy, "output", "") or ""),
            commands=list(getattr(legacy, "commands", None) or []),
            block_estimate=int(getattr(legacy, "block_estimate", 0) or 0),
            error=getattr(legacy, "error", None),
            execution_metadata=dict(getattr(legacy, "execution_metadata", None) or {}),
        )
