from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CaseMode(str, Enum):
    spec = "spec"
    world = "world"


class CaseSeverity(str, Enum):
    P0_safety = "P0-safety"
    P1_correctness = "P1-correctness"
    P2_routing = "P2-routing"
    P3_creative = "P3-creative"


class ToolCallExpectation(BaseModel):
    name: str
    arguments: dict[str, Any] | None = None


class SpecExpect(BaseModel):
    status: Literal["done", "failed"] | None = None
    max_steps: int | None = None
    must_call: list[ToolCallExpectation] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    must_call_in_order: list[str] = Field(default_factory=list)


class WorldExpect(BaseModel):
    sandbox_box: list[int] | None = Field(
        default=None, description="x1,y1,z1,x2,y2,z2; overrides global sandbox"
    )
    blocks_present: list[dict[str, Any]] = Field(default_factory=list)
    blocks_absent: list[dict[str, Any]] = Field(default_factory=list)
    player_not_buried: bool | None = None
    player_has_escape_path: dict[str, Any] | None = None


class EvalCase(BaseModel):
    id: str
    category: str
    severity: CaseSeverity = CaseSeverity.P1_correctness
    modes: list[CaseMode]
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)

    determinism: Literal["strict", "relaxed"] = "strict"
    retries_allowed: int = 0

    expect_spec: SpecExpect | None = None
    expect_world: WorldExpect | None = None

