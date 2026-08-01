"""Typed perception models and model-safe summaries.

Coordinates may exist in trusted plugin↔companion envelopes. Never feed raw
coords, block arrays, NBT, inventory contents, or claim owner names to the model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low", "none"]
Purpose = Literal[
    "finish_wall",
    "finish_floor",
    "paste_template",
    "interact",
    "model_context",
]


class BlockPos(BaseModel):
    x: int
    y: int
    z: int


class Pose(BaseModel):
    x: float
    y: float
    z: float
    yaw: float
    pitch: float


class Gaze(BaseModel):
    hit: bool
    material: str | None = None
    face: str | None = None
    pos: BlockPos | None = None
    distance_blocks: float = 0.0


class Held(BaseModel):
    material: str | None = None
    is_block: bool = False


class PolicyFacet(BaseModel):
    can_build_at_target: bool = True
    in_claim: bool = False
    has_build_permission: bool = True
    deny_reason: str | None = None


class BudgetUsed(BaseModel):
    cells_sampled: int = 0
    elapsed_ms: int = 0
    truncated: bool = False
    bytes: int = 0


class Opening(BaseModel):
    axis: Literal["x", "z"]
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    min_z: int
    max_z: int
    length: int
    height: int
    air_cells: int
    end_a_material: str | None = None
    end_b_material: str | None = None
    suggested_material: str | None = None
    confidence: Confidence = "none"


class Surface(BaseModel):
    axis: Literal["x", "y", "z"]
    normal: str
    min_x: int = 0
    max_x: int = 0
    min_y: int = 0
    max_y: int = 0
    min_z: int = 0
    max_z: int = 0
    width: int
    height: int
    material: str | None = None
    confidence: Confidence = "none"


class Clearance(BaseModel):
    min_x: int = 0
    max_x: int = 0
    min_y: int = 0
    max_y: int = 0
    min_z: int = 0
    max_z: int = 0
    width: int
    height: int
    depth: int
    air_cells: int
    confidence: Confidence = "none"


class PaletteEntry(BaseModel):
    material: str
    count: int


class Nearby(BaseModel):
    friendly_count: int = 0
    hostile_count: int = 0
    interactable: str | None = None


class FastObservationV1(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    observation_id: str
    captured_at_ms: int
    world: str
    pose: Pose
    gaze: Gaze
    held: Held
    policy: PolicyFacet
    fingerprint: str = Field(min_length=8, max_length=64)
    capture_ms: int = 0


class SemanticSceneV1(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    observation_id: str
    parent_observation_id: str
    captured_at_ms: int
    purpose: Purpose
    budget: BudgetUsed = Field(default_factory=BudgetUsed)
    surface: Surface | None = None
    openings: list[Opening] = Field(default_factory=list, max_length=3)
    clearance: Clearance | None = None
    palette: list[PaletteEntry] = Field(default_factory=list, max_length=8)
    nearby: Nearby | None = None
    policy: PolicyFacet | None = None
    fingerprint: str = Field(min_length=8, max_length=64)
    confidence: Confidence = "none"


def parse_fast_observation(raw: dict[str, Any] | None) -> FastObservationV1 | None:
    if not raw:
        return None
    try:
        return FastObservationV1.model_validate(raw)
    except Exception:
        return None


def parse_semantic_scene(raw: dict[str, Any] | None) -> SemanticSceneV1 | None:
    if not raw:
        return None
    try:
        return SemanticSceneV1.model_validate(raw)
    except Exception:
        return None


def model_safe_summary(
    fast: FastObservationV1 | None,
    scene: SemanticSceneV1 | None = None,
) -> str:
    """Compact semantic summary with no coordinates for the local model."""
    parts: list[str] = []
    if fast is not None:
        if fast.gaze.hit and fast.gaze.material:
            face = f" {fast.gaze.face}_face" if fast.gaze.face else ""
            parts.append(f"looking_at={fast.gaze.material}{face}")
        else:
            parts.append("looking_at=none")
        if fast.held.is_block and fast.held.material:
            parts.append(f"holding={fast.held.material}")
        else:
            parts.append("holding=none")
        parts.append(
            "can_build=true" if fast.policy.can_build_at_target else "can_build=false"
        )
    if scene is not None and scene.openings:
        top = scene.openings[0]
        material = top.suggested_material or "unknown"
        parts.append(
            f"opening={top.length} wide × {top.height} high, "
            f"{top.confidence} confidence, fill={material}"
        )
    elif scene is not None and scene.surface is not None:
        surf = scene.surface
        parts.append(
            f"surface={surf.width}×{surf.height} {surf.material or 'unknown'}, "
            f"{surf.confidence} confidence"
        )
    if scene is not None and scene.clearance is not None:
        c = scene.clearance
        parts.append(f"clearance={c.width}×{c.height}×{c.depth}")
    return "; ".join(parts) if parts else ""


def best_opening(scene: SemanticSceneV1 | None) -> Opening | None:
    if scene is None or not scene.openings:
        return None
    order = {"high": 3, "medium": 2, "low": 1, "none": 0}
    return max(scene.openings, key=lambda item: (order.get(item.confidence, 0), item.air_cells))
