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
    ("a place for chickens to live", "chicken_coop_small", "farm_pen"),
    ("sheep pen", "sheep_pen_medium", "farm_pen"),
    ("cow barn", "cow_barn_medium", "farm_pen"),
    ("wheat field", "wheat_farm_small", "farm"),
    ("sugarcane farm", "sugarcane_farm_small", "farm"),
    ("pumpkin patch", "pumpkin_farm_small", "farm"),
    ("village well", "well_village", "utility"),
    ("lighthouse by the sea", "lighthouse_short", "infrastructure"),
    ("suspension bridge", "bridge_wood_suspension", "bridge"),
    ("short oak bridge", "bridge_oak_short", "bridge"),
    ("medieval gate", "gatehouse", "fortress"),
    ("small keep castle", "castle_small_keep", "castle"),
    ("beach hut", "beach_hut", "house"),
    ("igloo", "igloo_small", "house"),
    ("bakery shop", "bakery_small", "house"),
    ("market stall", "market_stall", "house"),
    ("windmill", "windmill_small", "farm"),
    ("water mill", "mill_water", "farm"),
    ("gazebo in the garden", "gazebo_oak", "decoration"),
    ("stone archway", "archway_stone", "decoration"),
    ("bell tower", "bell_tower", "fortress"),
    ("watch tower tall", "watchtower_tall", "fortress"),
    ("greenhouse", "greenhouse_small", "farm"),
    ("horse stable small", "horse_stable_small", "farm"),
    ("rabbit hutch", "rabbit_hutch_small", "farm"),
    ("treehouse oak", "treehouse_oak", "house"),
    ("wizard tower", "wizard_tower", "fortress"),
    ("enchanting room", "enchanting_room", "utility"),
    ("armory", "armory_small", "utility"),
    ("tavern inn", "tavern_small", "house"),
    ("graveyard", "graveyard_small", "decoration"),
    ("bench row", "bench_row", "decoration"),
    ("flag pole", "flag_pole", "decoration"),
    ("fountain", "fountain_small", "decoration"),
    ("kelp farm", "kelp_farm_small", "farm"),
    ("herb garden", "herb_garden", "farm"),
    ("rock arch", "rock_arch", "nature_terrain"),
    ("zen garden", "zen_garden", "decoration"),
    ("apartment block", "apartment_block", "house"),
    ("guard post", "guard_post", "fortress"),
    ("library", "library_small", "house"),
    ("blacksmith", "blacksmith_shop", "house"),
    ("inn small", "inn_small", "house"),
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
