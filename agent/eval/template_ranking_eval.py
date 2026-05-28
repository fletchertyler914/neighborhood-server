"""Ambiguity eval prompts for hybrid template ranking (offline, no RCON)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Kid-friendly / ambiguous prompts with expected top-1 template id.
CASES: list[tuple[str, str, str]] = [
    ("build a small chicken coop", "chicken_coop_small", "farm_pen"),
    ("make a pig pen", "pig_pen_small", "farm_pen"),
    ("stone fortress", "castle_small_keep", "castle"),
    ("wooden bridge", "bridge_oak_short", "bridge"),
    ("watch tower", "watchtower_tall", "castle"),
    ("log cabin", "cabin_log", "house"),
    ("bee place", "bee_apiary_small", "farm_pen"),
    ("big oak tree", "tree_oak_large", "general"),
    ("fountain in the square", "fountain_small", "general"),
    ("hedge maze", "maze_hedge_small", "general"),
]


def run_eval() -> dict[str, object]:
    os.environ.setdefault("TEMPLATE_EMBEDDING_BACKEND", "disabled")
    from agent.templates import catalog as tc
    from agent.templates.ranking import resolve_template

    tc.reload_catalog()
    passed = 0
    rows: list[dict[str, object]] = []
    for query, expected, intent in CASES:
        r = resolve_template(query, intent_family=intent)
        ok = r.selected_template_id == expected
        if ok:
            passed += 1
        rows.append(
            {
                "query": query,
                "expected": expected,
                "got": r.selected_template_id,
                "confidence": r.confidence,
                "ok": ok,
            }
        )
    return {
        "total": len(CASES),
        "passed": passed,
        "failed": len(CASES) - passed,
        "cases": rows,
    }


def main() -> None:
    report = run_eval()
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
