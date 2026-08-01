#!/usr/bin/env python3
"""Authoritative elite release gate with machine-readable artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "data" / "perception-evals"


def _run(cmd: list[str], *, timeout: int = 600) -> tuple[int, str]:
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return completed.returncode, out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--skip-soak", action="store_true", default=True)
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    out_dir = ARTIFACTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: list[dict] = []

    def stage(name: str, cmd: list[str], *, timeout: int = 600) -> bool:
        code, output = _run(cmd, timeout=timeout)
        (out_dir / f"{name}.log").write_text(output + "\n")
        ok = code == 0
        stages.append({"name": name, "ok": ok, "exit_code": code})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(output[-2000:])
        return ok

    ok = True
    ok = stage(
        "01_unit",
        [
            "python3",
            "-m",
            "pytest",
            "tests/test_perception_contract.py",
            "tests/test_greenfield_companion.py",
            "tests/test_companion_dialogue.py",
            "tests/test_companion_gateway.py",
            "-q",
        ],
    ) and ok
    if not ok:
        _write_summary(out_dir, run_id, stages, False)
        return 1

    ok = stage(
        "02_perception_fast",
        ["python3", "-m", "evals.run_perception_offline", "--scenes", "40"],
    ) and ok
    if not ok:
        _write_summary(out_dir, run_id, stages, False)
        return 1

    ok = stage("03_companion_gate", ["make", "companion-gate"], timeout=900) and ok
    if not ok:
        _write_summary(out_dir, run_id, stages, False)
        return 1

    if not args.skip_live:
        ok = stage(
            "04_perception_live",
            ["make", "perception-live"],
            timeout=600,
        ) and ok
        if not ok:
            _write_summary(out_dir, run_id, stages, False)
            return 1
        ok = stage("05_companion_live", ["make", "companion-live"], timeout=900) and ok
        if not ok:
            _write_summary(out_dir, run_id, stages, False)
            return 1
        ok = stage(
            "06_companion_live_dialogue",
            ["make", "companion-live-dialogue"],
            timeout=600,
        ) and ok
        if not ok:
            _write_summary(out_dir, run_id, stages, False)
            return 1

    if not args.skip_soak:
        ok = stage(
            "06_soak_note",
            ["python3", "-c", "print('soak skipped unless --skip-soak=false')"],
        ) and ok

    _write_summary(out_dir, run_id, stages, ok)
    print(f"ELITE GATE: {'PASS' if ok else 'FAIL'} artifacts={out_dir}")
    return 0 if ok else 1


def _write_summary(out_dir: Path, run_id: str, stages: list[dict], ok: bool) -> None:
    summary = {
        "run_id": run_id,
        "ok": ok,
        "stages": stages,
        "created_at_ms": int(time.time() * 1000),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    latest = ARTIFACTS / "latest.json"
    latest.write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
