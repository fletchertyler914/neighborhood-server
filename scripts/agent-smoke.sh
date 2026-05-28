#!/usr/bin/env bash
# Representative natural-language smoke test through the real mc-agent
# /v1/jobs endpoint. Runs from inside the mc-agent container so it can reach the
# private orchestrator service without publishing ports.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PLAYER="${AGENT_SMOKE_PLAYER:-firecrab93}"
BASE_X="${AGENT_SMOKE_X:-2000}"
BASE_Y="${AGENT_SMOKE_Y:--60}"
BASE_Z="${AGENT_SMOKE_Z:-2000}"

docker exec \
  -e AGENT_SMOKE_PLAYER="$PLAYER" \
  -e AGENT_SMOKE_X="$BASE_X" \
  -e AGENT_SMOKE_Y="$BASE_Y" \
  -e AGENT_SMOKE_Z="$BASE_Z" \
  -i mc-agent python - <<'PY'
import json
import os
import time
import urllib.request

base = "http://127.0.0.1:8787/v1/jobs"
token = os.environ.get("AGENT_API_TOKEN", "")
player = os.environ.get("AGENT_SMOKE_PLAYER", "firecrab93")
base_x = float(os.environ.get("AGENT_SMOKE_X", "2000"))
base_y = float(os.environ.get("AGENT_SMOKE_Y", "-60"))
base_z = float(os.environ.get("AGENT_SMOKE_Z", "2000"))
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

prompts = [
    ("build me a small cabin", ["paste_template", "build_house"], "house/cabin"),
    ("build a two-story house with stairs", ["paste_template", "build_house"], "house/two-story"),
    ("I want a tavern", ["paste_template"], "house/tavern"),
    ("make a cottage in front of me", ["paste_template", "build_house"], "house/cottage"),
    ("plant me a treehouse", ["paste_template"], "house/treehouse"),
    ("apartment building please", ["paste_template", "build_house"], "house/apartment"),
    ("build a wooden bridge", ["paste_template", "build_bridge"], "bridge/wood"),
    ("I need a stone bridge across the river", ["paste_template", "build_bridge"], "bridge/stone"),
    ("a rope bridge", ["paste_template"], "bridge/rope"),
    ("build a castle", ["paste_template", "build_castle"], "castle/generic"),
    ("I want a watchtower", ["paste_template"], "tower/watchtower"),
    ("make a wizard tower", ["paste_template"], "tower/wizard"),
    ("build a fortress", ["paste_template", "build_castle"], "fortress"),
    ("a lighthouse", ["paste_template"], "lighthouse"),
    ("make a chicken coop", ["paste_template", "build_animal_pen"], "coop/chicken"),
    ("a place for chickens to live", ["paste_template", "build_animal_pen"], "coop/semantic"),
    ("build a horse stable", ["paste_template", "build_animal_pen"], "stable/horse"),
    ("plant a big oak tree", ["paste_template"], "nature/tree"),
    ("a fountain", ["paste_template"], "decor/fountain"),
    ("build a hedge maze", ["paste_template"], "decor/maze"),
    ("build a windmill", ["paste_template"], "decor/windmill"),
    ("summon 5 chickens", ["summon_entity"], "mob/chickens"),
    ("summon a horse", ["summon_entity"], "mob/horse"),
    ("give me a few sheep", ["summon_entity"], "mob/sheep"),
    ("set time to day", ["set_time"], "world/time"),
    ("make it rain", ["set_weather"], "world/weather"),
]

results = []
for idx, (prompt, expected_any, label) in enumerate(prompts, 1):
    body = {
        "player": player,
        "uuid": f"agent-smoke-{idx}",
        "world": "minecraft:overworld",
        "x": base_x + idx * 32,
        "y": base_y,
        "z": base_z,
        "gamemode": "creative",
        "prompt": prompt,
        "eval_mode": True,
    }
    req = urllib.request.Request(base, data=json.dumps(body).encode(), headers=headers, method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
        tools = [call.get("name", "") for call in payload.get("tool_calls", [])]
        args = [call.get("arguments", {}) for call in payload.get("tool_calls", [])]
        template = ""
        for name, arg in zip(tools, args):
            if name == "paste_template_at_player":
                template = str(arg.get("template_id") or "")
                break
        matched = any(any(expected in name for name in tools) for expected in expected_any)
        ok = payload.get("status") == "done" and matched
        results.append(
            {
                "label": label,
                "status": payload.get("status"),
                "tools": tools,
                "template": template,
                "seconds": round(time.time() - started, 1),
                "ok": ok,
            }
        )
    except Exception as exc:  # noqa: BLE001 - smoke test should report all failures
        results.append(
            {
                "label": label,
                "status": "ERROR",
                "tools": [f"{type(exc).__name__}: {exc}"],
                "template": "",
                "seconds": round(time.time() - started, 1),
                "ok": False,
            }
        )

print(f"{'#':>2}  {'label':22} {'status':8} {'tools':40} {'template':24} {'sec':>5}  ok")
print("-" * 120)
for idx, row in enumerate(results, 1):
    print(
        f"{idx:>2}. {row['label']:22} {str(row['status']):8} "
        f"{','.join(row['tools'])[:40]:40} {row['template'][:24]:24} "
        f"{row['seconds']:>5}  {'OK' if row['ok'] else 'X'}"
    )

passed = sum(1 for row in results if row["ok"])
print()
print(f"PASSED: {passed}/{len(results)}")
raise SystemExit(0 if passed == len(results) else 1)
PY
