"""L2: Live core-tool evals — no LLM. Gate before model bake-off.

Usage (host, stack up, player online)::

  ./mc.sh backup
  PYTHONPATH=. python3 -m agent.eval.live_tools --player firecrab93
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Host default: docker exec rcon-cli (no secret mount needed).
os.environ.setdefault("RCON_MODE", "exec")
os.environ.setdefault("MC_CONTAINER", "mc-lan")


@dataclass
class CaseResult:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


def _tp(player: str, x: int, y: int, z: int) -> None:
    from agent.dispatch import execute

    execute(
        "run_command",
        {"command": f"tp {player} {x} {y} {z}"},
        core_only=True,
    )
    time.sleep(0.5)


def _run_cases(player: str, sx: int, sy: int, sz: int) -> list[CaseResult]:
    from agent.dispatch import execute

    results: list[CaseResult] = []

    def case(name: str, fn) -> None:
        t0 = time.time()
        try:
            ok, detail = fn()
            results.append(CaseResult(name, ok, time.time() - t0, detail))
        except Exception as exc:  # noqa: BLE001
            results.append(CaseResult(name, False, time.time() - t0, f"{type(exc).__name__}: {exc}"))

    def check_preflight():
        r = execute("preflight", {})
        return r.ok, r.summary()

    def check_list():
        r = execute("list_players", {})
        return r.ok and player in (r.output or ""), r.summary()

    def check_time():
        r = execute("set_time", {"value": "day"})
        return r.ok, r.summary()

    def check_weather():
        r = execute("set_weather", {"weather": "clear"})
        return r.ok, r.summary()

    def check_give():
        r = execute("give_item", {"player": player, "item": "dirt", "count": 1})
        return r.ok, r.summary()

    def check_list_templates():
        r = execute("list_templates", {})
        return r.ok, r.summary()

    def check_platform():
        cx, cy, cz = sx + 8, sy, sz + 8
        r = execute(
            "build_platform",
            {
                "center_x": cx,
                "y": cy,
                "center_z": cz,
                "width": 5,
                "depth": 5,
                "block": "stone",
            },
        )
        return r.ok, r.summary()

    def check_summon():
        r = execute(
            "summon_entity",
            {"entity": "chicken", "x": sx + 10, "y": sy + 1, "z": sz + 10, "count": 2},
        )
        return r.ok, r.summary()

    def check_sphere():
        _tp(player, sx + 20, sy + 1, sz + 20)
        r = execute(
            "fawe_sphere_at_player",
            {"player": player, "block": "glass", "radius": 3},
        )
        return r.ok, r.summary()

    def check_cyl():
        _tp(player, sx + 30, sy + 1, sz + 30)
        r = execute(
            "fawe_cyl_at_player",
            {"player": player, "block": "cobblestone", "radius": 3, "height": 4, "hollow": True},
        )
        return r.ok, r.summary()

    def check_paste():
        _tp(player, sx + 45, sy + 1, sz + 45)
        # Face south for predictable paste
        execute("run_command", {"command": f"execute as {player} at @s run tp @s ~ ~ ~ 0 0"})
        time.sleep(0.3)
        r = execute(
            "paste_template_at_player",
            {"player": player, "template_id": "chicken coop"},
        )
        return r.ok, r.summary()

    def check_run_command():
        r = execute("run_command", {"command": "list"})
        return r.ok, r.summary()

    case("preflight", check_preflight)
    case("list_players", check_list)
    case("set_time", check_time)
    case("set_weather", check_weather)
    case("give_item", check_give)
    case("list_templates", check_list_templates)
    case("build_platform", check_platform)
    case("summon_entity", check_summon)
    case("fawe_sphere_at_player", check_sphere)
    case("fawe_cyl_at_player", check_cyl)
    case("paste_template_at_player", check_paste)
    case("run_command", check_run_command)
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L2 live core-tool evals (no LLM)")
    preferred = (
        os.environ.get("AGENT_LIVE_PLAYER")
        or os.environ.get("AGENT_LIVE_TOOL_PLAYER")
        or "firecrab93"
    ).strip()
    p.add_argument("--player", default=os.environ.get("AGENT_LIVE_TOOL_PLAYER", ""))
    p.add_argument(
        "--sandbox",
        # Dedicated remote pad (aligned with evals/run_live.py) — not spawn/ocean.
        default=os.environ.get("AGENT_LIVE_TOOL_SANDBOX", "12500,96,12500"),
        help="x,y,z sandbox origin",
    )
    p.add_argument("--out", default="data/bakeoff/live_tools.json")
    args = p.parse_args(argv)

    player = args.player.strip() or preferred
    if not player:
        print("ERROR: no player — join as firecrab93 or pass --player", file=sys.stderr)
        return 2

    parts = [int(x.strip()) for x in args.sandbox.split(",")]
    if len(parts) != 3:
        print("ERROR: --sandbox must be x,y,z", file=sys.stderr)
        return 2
    sx, sy, sz = parts
    cx, cz = sx + 25, sz + 25
    feet_y = sy + 1

    print(f"live_tools: player={player} sandbox={sx},{sy},{sz}")
    from agent.dispatch import execute

    # Load chunks, build solid pad FIRST, then teleport onto it (never void/ocean).
    execute(
        "run_command",
        {"command": f"forceload add {sx - 16} {sz - 16} {sx + 80} {sz + 80}"},
    )
    # Clear air in y-slices (vanilla /fill max 32768; full column would overflow).
    for yy in range(sy + 1, sy + 41, 8):
        y2 = min(sy + 40, yy + 7)
        execute(
            "run_command",
            {
                "command": (
                    f"fill {cx - 30} {yy} {cz - 30} {cx + 30} {y2} {cz + 30} air"
                )
            },
        )
    # Thick stone base + grass top.
    execute(
        "run_command",
        {
            "command": (
                f"fill {cx - 30} {sy - 3} {cz - 30} {cx + 30} {sy} {cz + 30} stone"
            )
        },
    )
    execute(
        "build_platform",
        {
            "center_x": cx,
            "y": sy,
            "center_z": cz,
            "width": 60,
            "depth": 60,
            "block": "grass_block",
        },
    )
    _tp(player, cx, feet_y, cz)
    time.sleep(0.5)

    results = _run_cases(player, sx, sy, sz)
    passed = sum(1 for r in results if r.ok)
    total = len(results)

    print(f"{'#':>2}  {'case':28} {'sec':>6}  ok  detail")
    print("-" * 100)
    for i, r in enumerate(results, 1):
        print(
            f"{i:>2}. {r.name:28} {r.seconds:6.1f}  "
            f"{'OK' if r.ok else 'X '}  {r.detail[:70]}"
        )
    print()
    print(f"PASSED: {passed}/{total}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "player": player,
                "sandbox": [sx, sy, sz],
                "passed": passed,
                "total": total,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
