"""L5: Live agent eval gate — NL → companion /v1/jobs → tool success.

Runs inside mc-agent container (or host with AGENT_GATE_URL).

  docker exec -e AGENT_API_TOKEN=... -e AGENT_GATE_PLAYER=firecrab93 \\
    mc-agent python -m agent.eval.agent_gate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

CASES = [
    ("set time to day", ["set_time"]),
    ("make it rain", ["set_weather"]),
    ("give me a dirt block", ["give_item"]),
    ("summon 2 chickens", ["summon_entity"]),
    ("make a chicken coop", ["paste_template_at_player"]),
    ("build a glass sphere radius 3", ["fawe_sphere_at_player", "build_sphere"]),
    ("list templates", ["list_templates"]),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("AGENT_GATE_URL", "http://127.0.0.1:8787"))
    p.add_argument("--player", default=os.environ.get("AGENT_GATE_PLAYER", ""))
    p.add_argument("--token", default=os.environ.get("AGENT_API_TOKEN", ""))
    p.add_argument("--out", default="/app/data/bakeoff/agent_gate.json")
    args = p.parse_args()

    if not args.player:
        print("ERROR: set AGENT_GATE_PLAYER", file=sys.stderr)
        return 2
    if not args.token:
        print("ERROR: set AGENT_API_TOKEN", file=sys.stderr)
        return 2

    base = args.url.rstrip("/") + "/v1/jobs"
    headers = {
        "Authorization": f"Bearer {args.token}",
        "Content-Type": "application/json",
    }
    results = []
    for i, (prompt, expected) in enumerate(CASES):
        body = {
            "player": args.player,
            "uuid": f"agent-gate-{i}",
            "world": "minecraft:overworld",
            "x": 2200.0 + i * 32,
            "y": -59.0,
            "z": 2200.0,
            "gamemode": "creative",
            "prompt": prompt,
            "eval_mode": True,
        }
        req = urllib.request.Request(
            base, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
            tools = [c.get("name", "") for c in payload.get("tool_calls") or []]
            matched = any(any(e in t for t in tools) for e in expected)
            ok = payload.get("status") == "done" and matched
            results.append(
                {
                    "prompt": prompt,
                    "tools": tools,
                    "status": payload.get("status"),
                    "model": payload.get("model"),
                    "seconds": round(time.time() - t0, 2),
                    "ok": ok,
                    "message": (payload.get("message") or "")[:120],
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "prompt": prompt,
                    "tools": [],
                    "status": "ERROR",
                    "model": "",
                    "seconds": round(time.time() - t0, 2),
                    "ok": False,
                    "message": str(exc),
                }
            )

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print(f"{'#':>2}  {'prompt':40} {'tools':36} {'sec':>5} ok")
    print("-" * 100)
    for i, r in enumerate(results, 1):
        print(
            f"{i:>2}. {r['prompt'][:40]:40} {','.join(r['tools'])[:36]:36} "
            f"{r['seconds']:>5}  {'OK' if r['ok'] else 'X'}"
        )
    print(f"\nPASSED: {passed}/{total}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "results": results}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    # Gate: ≥90%
    return 0 if passed / max(total, 1) >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
