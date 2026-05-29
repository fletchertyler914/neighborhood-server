"""Corpus eval case models — NL prompts with tool + world probes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


LanguageStyle = Literal[
    "direct",
    "casual",
    "polite",
    "typoed",
    "verbose",
    "minimal",
    "bedrock",
    "adversarial",
]

WorldProbeKind = Literal[
    "template_built",
    "shape_built",
    "mob_count",
    "entity_count_in_box",
    "shaft_dug",
    "setting",
    "inventory_has",
    "palette_histogram",
    "count_block_in_box",
    "structural_check",
    "region_hash_matches",
    "none",
]


class ToolExpectAny(BaseModel):
    """At least one tool call must match name + one of arguments_any subsets."""

    name: str
    arguments_any: list[dict[str, Any]] = Field(default_factory=list)


class WorldProbe(BaseModel):
    kind: WorldProbeKind
    anchor: Literal["player", "player_forward", "sandbox_center"] = "player_forward"
    # template_built / shape_built
    template_id: str | None = None
    sample_blocks: list[str] = Field(default_factory=list)
    min_matches: int = 2
    shape: Literal["platform", "cylinder", "sphere"] | None = None
    block: str | None = None
    radius: int | None = None
    width: int | None = None
    platform_depth: int | None = None
    height: int | None = None
    hollow: bool | None = None
    # auditor bbox / structural checks
    bbox_width: int | None = None
    bbox_height: int | None = None
    bbox_depth: int | None = None
    min_counts: dict[str, int] = Field(default_factory=dict)
    max_counts: dict[str, int] = Field(default_factory=dict)
    check: str | None = None
    content_hash: str | None = None
    # mob_count
    entity: str | None = None
    count_min: int = 1
    count_max: int | None = None
    search_radius: int = 12
    # shaft_dug
    shaft_depth: int | None = None
    # setting
    setting: Literal["time", "weather", "gamemode"] | None = None
    value: str | None = None
    # inventory_has
    item: str | None = None
    min_count: int = 1


class CorpusExpect(BaseModel):
    status: Literal["done", "failed"] | None = "done"
    max_steps: int | None = 14
    tool_any: list[ToolExpectAny] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    world_probe: WorldProbe | None = None


class CorpusCase(BaseModel):
    id: str
    category: str
    intent: str
    language_style: LanguageStyle = "direct"
    prompt: str
    expect: CorpusExpect = Field(default_factory=CorpusExpect)
    tags: list[str] = Field(default_factory=list)
