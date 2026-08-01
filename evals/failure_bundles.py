"""Bounded local failure bundles + promote/replay helpers."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "perception-runs"
FIXTURES = ROOT / "evals" / "fixtures" / "perception"


def write_bundle(
    *,
    prompt: str,
    route: str,
    ok: bool,
    message: str,
    observation: dict[str, Any] | None = None,
    scene: dict[str, Any] | None = None,
    phase: dict[str, Any] | None = None,
    reason: str = "",
) -> Path:
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    path = RUNS / run_id
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "created_at_ms": int(time.time() * 1000),
        "prompt": prompt[:500],
        "route": route,
        "ok": ok,
        "message": message[:160],
        "reason": reason[:200],
        "observation": _strip_sensitive(observation),
        "scene": _strip_sensitive(scene),
        "phase": phase or {},
    }
    (path / "bundle.json").write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _strip_sensitive(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    data = dict(raw)
    # Keep pose quantized only.
    pose = data.get("pose")
    if isinstance(pose, dict):
        data["pose"] = {
            "x": int(pose.get("x", 0)),
            "y": int(pose.get("y", 0)),
            "z": int(pose.get("z", 0)),
            "yaw": int(round(float(pose.get("yaw", 0)) / 90.0) * 90),
            "pitch": 0,
        }
    data.pop("claim_owner", None)
    data.pop("inventory", None)
    return data


def promote(run_id: str, name: str) -> Path:
    src = RUNS / run_id / "bundle.json"
    if not src.exists():
        raise SystemExit(f"missing bundle: {src}")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    dest = FIXTURES / f"{name}.json"
    data = json.loads(src.read_text())
    data["promoted_name"] = name
    dest.write_text(json.dumps(data, indent=2) + "\n")
    return dest


def replay(run_id: str) -> int:
    from companion.routing import route

    src = RUNS / run_id / "bundle.json"
    if not src.exists():
        # allow fixture name
        fixture = FIXTURES / f"{run_id}.json"
        if not fixture.exists():
            raise SystemExit(f"missing bundle/fixture: {run_id}")
        src = fixture
    data = json.loads(src.read_text())
    prompt = data["prompt"]
    decision = route(prompt, "replay")
    print(
        f"REPLAY {run_id}: route={decision.route} "
        f"tool={decision.action.tool if decision.action else None} "
        f"args={decision.action.arguments if decision.action else decision.message}"
    )
    return 0


def report() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    bundles = sorted(RUNS.glob("*/bundle.json"), reverse=True)[:20]
    print(f"latest_bundles={len(bundles)}")
    for path in bundles:
        data = json.loads(path.read_text())
        print(
            f"- {data.get('run_id')} ok={data.get('ok')} route={data.get('route')} "
            f"prompt={data.get('prompt')!r} msg={data.get('message')!r}"
        )
    return 0


def prune(days: int = 7) -> int:
    if not RUNS.exists():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for path in RUNS.iterdir():
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    print(f"pruned={removed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    p = sub.add_parser("promote")
    p.add_argument("--run", required=True)
    p.add_argument("--name", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--run", required=True)
    sub.add_parser("prune")
    args = parser.parse_args()
    if args.cmd == "report":
        return report()
    if args.cmd == "promote":
        dest = promote(args.run, args.name)
        print(f"promoted -> {dest}")
        return 0
    if args.cmd == "replay":
        return replay(args.run)
    if args.cmd == "prune":
        return prune()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
