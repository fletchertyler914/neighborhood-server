#!/usr/bin/env python3
"""L3: Live model bake-off — one model at a time, Metal/MLX preflight first.

Fairness rules:
  - Never run two models concurrently
  - Unload all resident models before each candidate
  - Validate GPU/MLX residency before scoring that candidate
  - Cap num_ctx=8192 for every request

Usage:
  PYTHONPATH=. python3 scripts/validate_metal_inference.py --model gemma4:12b-mlx
  PYTHONPATH=. python3 scripts/model_bakeoff.py --live \\
    --models gemma4:12b-mlx,ornith:35b --player firecrab93
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("RCON_MODE", "exec")
os.environ.setdefault("MC_CONTAINER", "mc-lan")

from agent.contracts.core import core_openai_schemas  # noqa: E402
from agent.dispatch import execute  # noqa: E402
from agent.job import JobRequest, build_user_message  # noqa: E402
from agent.llm.metal_preflight import NUM_CTX, unload_all, validate_model  # noqa: E402

SYSTEM = """/no_think
You are a Minecraft companion. Call exactly one tool.
Prefer paste_template_at_player for named structures.
Prefer fawe_sphere_at_player / fawe_cyl_at_player for shapes.
Use set_time, set_weather, give_item, summon_entity for those intents.
"""

CASES = [
    ("set time to day", ["set_time"], "admin/time"),
    ("make it rain", ["set_weather"], "admin/weather"),
    ("give me a diamond pickaxe", ["give_item"], "admin/give"),
    ("summon 3 chickens", ["summon_entity"], "mobs/chicken"),
    ("build a stone platform under me", ["build_platform"], "build/platform"),
    ("make a glass sphere around me radius 4", ["fawe_sphere_at_player"], "build/sphere"),
    ("build a hollow cobblestone cylinder radius 3 height 5", ["fawe_cyl_at_player"], "build/cyl"),
    ("make a chicken coop", ["paste_template_at_player"], "build/coop"),
    ("a place for chickens to live", ["paste_template_at_player"], "build/coop-nl"),
    ("build a small cabin", ["paste_template_at_player"], "build/cabin"),
]


def _chat(base: str, model: str, messages: list, tools: list) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,
        "options": {"num_ctx": NUM_CTX, "num_predict": 1024},
        "keep_alive": "10m",
        "think": False,
    }
    with httpx.Client(timeout=90.0) as client:
        r = client.post(f"{base}/v1/chat/completions", json=payload)
        r.raise_for_status()
        return r.json()


def _parse_tool(data: dict) -> tuple[str, dict]:
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    tcs = msg.get("tool_calls") or []
    if not tcs:
        return "", {}
    fn = tcs[0].get("function") or {}
    name = fn.get("name") or ""
    raw = fn.get("arguments") or "{}"
    args = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return name, args


def run_model_exclusive(
    *,
    base: str,
    model: str,
    player: str,
    sx: int,
    sy: int,
    sz: int,
    live: bool,
) -> tuple[list[dict], dict]:
    """Preflight → score → unload. Only this model may be resident."""

    print(f"\n{'=' * 60}")
    print(f"SEQUENTIAL SLOT: {model}")
    print(f"{'=' * 60}")

    pre = validate_model(base, model, unload_first=True)
    print(f"preflight {model}: {'PASS' if pre['ok'] else 'FAIL'}")
    for c in pre["checks"]:
        print(f"  [{'OK' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    if not pre["ok"]:
        raise RuntimeError(f"Metal/MLX preflight failed for {model}")

    tools = core_openai_schemas()
    rows: list[dict] = []
    for i, (prompt, expected, label) in enumerate(CASES):
        pad_x = sx + i * 40
        pad_z = sz
        req = JobRequest(
            player=player,
            uuid=f"bakeoff-{model.replace(':', '_')}-{i}",
            x=float(pad_x),
            y=float(sy + 1),
            z=float(pad_z),
            prompt=prompt,
            eval_mode=True,
        )
        if live:
            # Ensure a small solid pad under each case teleport.
            execute(
                "run_command",
                {
                    "command": (
                        f"fill {pad_x - 2} {sy - 1} {pad_z - 2} "
                        f"{pad_x + 2} {sy} {pad_z + 2} stone"
                    )
                },
            )
            execute(
                "run_command",
                {
                    "command": (
                        f"fill {pad_x - 2} {sy} {pad_z - 2} "
                        f"{pad_x + 2} {sy} {pad_z + 2} grass_block"
                    )
                },
            )
            execute(
                "run_command",
                {"command": f"tp {player} {pad_x + 0.5} {sy + 1} {pad_z + 0.5}"},
            )
            time.sleep(0.4)

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_message(req)},
        ]
        t0 = time.time()
        err = ""
        name, args = "", {}
        world_ok = False
        try:
            data = _chat(base, model, messages, tools)
            name, args = _parse_tool(data)
            if name in (
                "give_item",
                "paste_template_at_player",
                "fawe_sphere_at_player",
                "fawe_cyl_at_player",
            ) or name.endswith("_at_player"):
                args.setdefault("player", player)
            if name == "summon_entity":
                args.setdefault("x", pad_x)
                args.setdefault("y", sy + 1)
                args.setdefault("z", pad_z)
            if name == "build_platform":
                args.setdefault("center_x", pad_x)
                args.setdefault("y", sy)
                args.setdefault("center_z", pad_z)
                args.setdefault("width", 5)
                args.setdefault("depth", 5)
                args.setdefault("block", "stone")
            if live and name:
                result = execute(name, args)
                world_ok = result.ok
                err = result.error or (result.output or "")[:120]
            elif name:
                world_ok = True
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        elapsed = time.time() - t0
        route_ok = any(e in name for e in expected)
        ok = route_ok and (world_ok if live else bool(name))
        rows.append(
            {
                "label": label,
                "prompt": prompt,
                "tool": name,
                "expected": expected,
                "route_ok": route_ok,
                "world_ok": world_ok,
                "ok": ok,
                "seconds": round(elapsed, 2),
                "detail": err,
                "arguments": args,
            }
        )
        print(
            f"  {label:22} tool={name or '-':28} "
            f"{elapsed:5.1f}s  {'OK' if ok else 'X'}"
        )

    # Exclusive unload before next model
    with httpx.Client(timeout=60.0) as client:
        unload_all(client, base)
    print(f"unloaded {model} — slot free for next candidate")
    return rows, pre


def main() -> int:
    p = argparse.ArgumentParser(
        description="Sequential live bake-off (one model at a time)"
    )
    p.add_argument(
        "--models",
        default="gemma4:12b-mlx,ornith:35b",
        help="Comma-separated; run STRICTLY one after another",
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    p.add_argument(
        "--player",
        default=os.environ.get("AGENT_BAKEOFF_PLAYER")
        or os.environ.get("AGENT_LIVE_PLAYER")
        or "firecrab93",
    )
    # Dedicated remote pad — aligned with evals/run_live.py.
    p.add_argument("--sandbox", default="12500,96,12500")
    p.add_argument("--live", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--out", default="data/bakeoff/report.json")
    args = p.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    base = args.base_url.replace("host.docker.internal", "127.0.0.1")

    if args.preflight_only:
        failed = 0
        for model in models:
            # Sequential preflight too
            report = validate_model(base, model, unload_first=True)
            print(json.dumps(report, indent=2))
            with httpx.Client(timeout=60.0) as client:
                unload_all(client, base)
            if not report["ok"]:
                failed += 1
        return 1 if failed else 0

    player = (args.player or "").strip() or "firecrab93"
    if args.live and not player:
        print("ERROR: --live needs an online --player", file=sys.stderr)
        return 2

    sx, sy, sz = [int(x) for x in args.sandbox.split(",")]
    if args.live:
        execute(
            "run_command",
            {"command": f"forceload add {sx - 32} {sz - 32} {sx + 400} {sz + 64}"},
        )
        # Build the runway pad BEFORE teleporting — never drop into ocean/void.
        execute(
            "build_platform",
            {
                "center_x": sx + 100,
                "y": sy,
                "center_z": sz,
                "width": 220,
                "depth": 40,
                "block": "grass_block",
            },
        )
        execute(
            "run_command",
            {"command": f"tp {player} {sx + 0.5} {sy + 1} {sz + 0.5}"},
        )
        time.sleep(1.0)

    report: dict = {
        "models": {},
        "live": args.live,
        "player": player,
        "mode": "sequential_exclusive",
        "num_ctx": NUM_CTX,
    }
    best_name, best_score = "", -1.0

    for model in models:
        try:
            rows, pre = run_model_exclusive(
                base=base,
                model=model,
                player=player or "Player",
                sx=sx,
                sy=sy,
                sz=sz,
                live=args.live,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ABORT {model}: {exc}", file=sys.stderr)
            report["models"][model] = {"error": str(exc), "passed": 0, "total": 0}
            with httpx.Client(timeout=60.0) as client:
                unload_all(client, base)
            continue

        passed = sum(1 for r in rows if r["ok"])
        total = len(rows)
        secs = sorted(r["seconds"] for r in rows) or [0.0]
        p50 = secs[len(secs) // 2]
        score = passed + (0.01 * (1.0 / max(p50, 0.01)))
        report["models"][model] = {
            "passed": passed,
            "total": total,
            "p50_sec": p50,
            "preflight": pre,
            "rows": rows,
        }
        print(f"\n{model}: {passed}/{total}  p50={p50:.1f}s")
        if score > best_score:
            best_score = score
            best_name = model

    report["winner"] = best_name
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWINNER: {best_name}")
    print(f"wrote {out}")
    print(f"Set LOCAL_LLM_MODEL={best_name} in .env")
    return 0 if best_name else 1


if __name__ == "__main__":
    raise SystemExit(main())
