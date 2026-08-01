#!/usr/bin/env python3
"""Offline perception gates: schema, model-safe summary, synthetic geometry, routing."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from companion.perception import (
    FastObservationV1,
    Gaze,
    Held,
    PolicyFacet,
    Pose,
    SemanticSceneV1,
    model_safe_summary,
    parse_fast_observation,
)
from companion.routing import route
from evals.perception_geometry import evaluate_scene, generate_synthetic_scenes

ROOT = Path(__file__).resolve().parents[1]


def _schema_cases() -> list[dict]:
    results = []
    fast = FastObservationV1(
        observation_id=str(uuid.uuid4()),
        captured_at_ms=int(time.time() * 1000),
        world="minecraft:overworld",
        pose=Pose(x=1.5, y=64.0, z=2.5, yaw=90.0, pitch=10.0),
        gaze=Gaze(hit=True, material="oak_planks", face="north", distance_blocks=3.2),
        held=Held(material="quartz_block", is_block=True),
        policy=PolicyFacet(can_build_at_target=True, in_claim=False, has_build_permission=True),
        fingerprint="abc12345deadbeef",
        capture_ms=1,
    )
    parsed = parse_fast_observation(fast.model_dump())
    results.append({"id": "schema.fast.roundtrip", "passed": parsed == fast, "detail": ""})
    summary = model_safe_summary(fast)
    has_coords = any(token in summary for token in ("1.5", "64.0", "2.5", "x=", "y=", "z="))
    results.append(
        {
            "id": "schema.summary.no_coords",
            "passed": (not has_coords) and "looking_at=oak_planks" in summary and "holding=quartz_block" in summary,
            "detail": summary,
        }
    )
    malformed = parse_fast_observation({"schema_version": "9.9"})
    results.append({"id": "schema.malformed.reject", "passed": malformed is None, "detail": ""})
    oversize = parse_fast_observation({**fast.model_dump(), "fingerprint": "x" * 200})
    results.append({"id": "schema.oversize.reject", "passed": oversize is None, "detail": ""})
    return results


def _routing_cases() -> list[dict]:
    cases = [
        ("finish this wall", "finish_wall", {}),
        ("finsh the wall in front of me", "finish_wall", {}),
        ("finish this wall 12 blocks high", "finish_wall", {"height": 12}),
        ("finish the quartz wall", "finish_wall", {"material": "quartz_block"}),
        ("finish this wall with quartz", "finish_wall", {"material": "quartz_block"}),
        ("build a quartz block wall between the oak planks", "finish_wall", {"material": "quartz_block"}),
        ("make it daytime", "set_time", {"time": "day"}),
    ]
    results = []
    for prompt, tool, args in cases:
        decision = route(prompt, "perc")
        ok = (
            decision.action is not None
            and decision.action.tool == tool
            and all(decision.action.arguments.get(k) == v for k, v in args.items())
        )
        results.append(
            {
                "id": f"route.{tool}.{prompt[:24].replace(' ', '_')}",
                "passed": ok,
                "detail": f"{decision.route} {decision.action.arguments if decision.action else decision.message}",
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=40)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "perception-evals" / "offline-latest.json",
    )
    args = parser.parse_args()

    results = []
    results.extend(_schema_cases())
    results.extend(_routing_cases())
    scenes = generate_synthetic_scenes(args.scenes)
    for scene in scenes:
        passed, detail = evaluate_scene(scene)
        results.append({"id": scene["id"], "passed": passed, "detail": detail})

    passed = sum(1 for item in results if item["passed"])
    summary = {
        "cases": len(results),
        "passed": passed,
        "accuracy": passed / len(results) if results else 0.0,
        "scene_cases": len(scenes),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PERCEPTION OFFLINE: {passed}/{len(results)} ({summary['accuracy']:.1%})")
    gates = (
        summary["cases"] >= 40
        and summary["scene_cases"] >= 40
        and summary["accuracy"] == 1.0
    )
    print(f"GATES: {'PASS' if gates else 'FAIL'}")
    return 0 if gates else 1


if __name__ == "__main__":
    raise SystemExit(main())
