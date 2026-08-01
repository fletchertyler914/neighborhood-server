from __future__ import annotations

import uuid

from companion.perception import (
    FastObservationV1,
    Gaze,
    Held,
    PolicyFacet,
    Pose,
    model_safe_summary,
    parse_fast_observation,
)
from companion.routing import route
from evals.perception_geometry import evaluate_scene, generate_synthetic_scenes


def test_fast_observation_roundtrip_and_summary() -> None:
    fast = FastObservationV1(
        observation_id=str(uuid.uuid4()),
        captured_at_ms=1,
        world="minecraft:overworld",
        pose=Pose(x=10.2, y=70.0, z=-3.4, yaw=180.0, pitch=5.0),
        gaze=Gaze(hit=True, material="oak_planks", face="east", distance_blocks=4.0),
        held=Held(material="quartz_block", is_block=True),
        policy=PolicyFacet(
            can_build_at_target=True, in_claim=False, has_build_permission=True
        ),
        fingerprint="1234567890abcdef",
        capture_ms=1,
    )
    assert parse_fast_observation(fast.model_dump()) == fast
    summary = model_safe_summary(fast)
    assert "looking_at=oak_planks east_face" in summary
    assert "holding=quartz_block" in summary
    assert "10.2" not in summary
    assert "-3.4" not in summary


def test_wall_routing_no_height_and_material() -> None:
    decision = route("finish this wall", "t1")
    assert decision.action is not None
    assert decision.action.tool == "finish_wall"
    assert decision.action.arguments == {}

    quartz = route("finish the quartz wall in front of me", "t2")
    assert quartz.action is not None
    assert quartz.action.arguments["material"] == "quartz_block"

    between = route("build a quartz block wall between the oak planks", "t3")
    assert between.action is not None
    assert between.action.tool == "finish_wall"
    assert between.action.arguments["material"] == "quartz_block"


def test_visible_opening_changes_sized_wall_to_finish() -> None:
    decision = route(
        "build a quartz wall 20 long 8 high",
        "opening-wall",
        has_finishable_wall=True,
    )
    assert decision.route == "perception.finish_visible_wall"
    assert decision.action is not None
    assert decision.action.tool == "finish_wall"
    assert decision.action.arguments == {"height": 8, "material": "quartz_block"}

    free_wall = route("build a quartz wall 20 long 8 high", "free-wall")
    assert free_wall.action is not None
    assert free_wall.action.tool == "place_shape"


def test_rewrite_wall_place_to_finish_from_scene() -> None:
    from companion.perception import Opening, SemanticSceneV1
    from companion.place_routing import (
        finishable_opening_present,
        rewrite_wall_place_to_finish,
    )

    scene = SemanticSceneV1(
        observation_id="o1",
        parent_observation_id="p1",
        captured_at_ms=1,
        purpose="finish_wall",
        openings=[
            Opening(
                axis="z",
                min_x=0,
                max_x=0,
                min_y=64,
                max_y=71,
                min_z=10,
                max_z=16,
                length=7,
                height=8,
                air_cells=42,
                suggested_material="oak_planks",
                confidence="high",
            )
        ],
        fingerprint="1234567890abcdef",
        confidence="high",
    )
    rewritten = rewrite_wall_place_to_finish(
        "job-rewrite",
        {"kind": "wall", "length": 20, "height": 8, "material": "stone"},
        scene,
    )
    assert rewritten is not None
    assert rewritten.action is not None
    assert rewritten.action.tool == "finish_wall"
    assert rewritten.action.arguments == {"height": 8, "material": "stone"}
    assert rewrite_wall_place_to_finish("j", {"kind": "wall"}, None) is None
    assert finishable_opening_present(scene) is True
    assert finishable_opening_present(None) is False
    busy = SemanticSceneV1(
        observation_id="o2",
        parent_observation_id="p1",
        captured_at_ms=1,
        purpose="finish_wall",
        openings=[],
        fingerprint="busy000000000000",
        confidence="none",
    )
    assert finishable_opening_present(busy) is False
    assert rewrite_wall_place_to_finish("j", {"kind": "wall", "height": 6}, busy) is None


def test_synthetic_open_face_scenes_pass() -> None:
    scenes = generate_synthetic_scenes(40)
    assert len(scenes) >= 40
    failures = []
    for scene in scenes:
        ok, detail = evaluate_scene(scene)
        if not ok:
            failures.append((scene["id"], detail))
    assert failures == []
