#!/usr/bin/env python3
"""Print high-priority non-gold / demoted basics for curated refill shopping.

Reads live ``agent/templates/catalog.json`` gold flags and the prioritized
gap tables from the refill shopping list (kept in sync with
``docs/CURATED_REFILL.md``).

Usage::

    make gold-gaps
    python3 scripts/list_gold_gaps.py
    python3 scripts/list_gold_gaps.py --prio P0
    python3 scripts/list_gold_gaps.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "agent" / "templates" / "catalog.json"

# Keep aligned with docs/CURATED_REFILL.md "High-value gaps".
GAPS: dict[str, list[tuple[str, str, str]]] = {
    "P0": [
        ("house_cottage_small", "house / cottage / tiny house", "Highest — generic house ask"),
        ("cabin_log", "log cabin", "eval + playbook staple"),
        ("chicken_coop_small", "chicken coop / hen house", "eval staple"),
        ("barn_red_large", "barn / red barn", "farm hub"),
        ("pig_pen_small", "pig pen", "animal trio with sheep"),
        ("sheep_pen_medium", "sheep pen", ""),
        ("bee_apiary_small", "bee house", ""),
        ("garden_plot", "garden / flower garden", "aliases rich; schem was junk"),
        ("market_stall", "market / shop stall", "typo aliases exist"),
        ("blacksmith_shop", "blacksmith", ""),
        ("tavern_small", "tavern", ""),
        ("workshop_small", "workshop", ""),
        ("castle_small_keep", "little castle", ""),
        ("watchtower_tall", "watchtower", ""),
        ("lighthouse_short", "lighthouse", ""),
        ("windmill_small", "windmill", ""),
        ("treehouse_oak", "treehouse", ""),
        ("well_village", "village well", ""),
    ],
    "P1": [
        ("cottage_medium", "medium / bigger cottage", "pair with small cottage"),
        ("modern_house_flat", "modern house", "clarify today"),
        ("igloo_small", "igloo", "clarify today"),
        ("bridge_rope", "rope bridge", "oak bridge already gold"),
        ("bridge_stone_long", "stone bridge", ""),
        ("pier_long", "long pier", "dock kept"),
        ("fishing_hut", "fishing hut", "seed-junk twin — replace"),
        ("bakery_small", "bakery", "seed-junk twin — replace"),
        ("storage_shed", "shed / storage", "seed-junk twin — replace"),
        ("mill_water", "water mill", "seed-junk twin — replace"),
        ("inn_small", "inn", ""),
        ("church_small", "church", ""),
        ("library_small", "library", ""),
        ("wizard_tower", "wizard tower", "clarify today"),
        ("greenhouse_small", "greenhouse", ""),
        ("fountain_small", "fountain", ""),
        ("gazebo_oak", "gazebo", ""),
        ("playground_small", "playground", ""),
        ("campground", "camp / campground", ""),
        ("sugarcane_farm_small", "sugarcane farm", "crop set incomplete"),
        ("cabin_stone", "stone cabin", "distinct schem or alias→cabin_log"),
    ],
    "P2": [
        ("townhouse_2story", "townhouse", ""),
        ("desert_house_small", "desert house", ""),
        ("mushroom_house", "mushroom house", ""),
        ("chicken_coop_large", "large chicken coop", ""),
        ("stable_large", "large stable", ""),
        ("pig_pen_large", "large pig pen", ""),
        ("kelp_farm_small", "kelp farm", ""),
        ("mushroom_farm_dark", "mushroom farm", ""),
        ("silo_grain", "grain silo", ""),
        ("bridge_wood_suspension", "suspension bridge", ""),
        ("warehouse_small", "warehouse", "junk twin"),
        ("gatehouse", "gatehouse", ""),
        ("guard_post", "guard post", ""),
        ("wooden_palisade", "palisade", ""),
        ("picnic_area", "picnic area", ""),
        ("bench_row", "park bench", ""),
        ("lamp_post_iron", "lamp post", ""),
        ("brewing_station", "potion station", "junk twin"),
        ("enchanting_room", "enchanting room", "junk twin"),
    ],
}

# SchemCraft CC-BY starters from CURATED_REFILL (optional shopping hints).
STARTERS: dict[str, str] = {
    # Showpieces / furnished bases only — not P0 basics (windmill/well/coop/…).
    "wizard_tower": "https://www.schemcraft.com/schematics/ultimate-enchanted-wizard-tower-survival-base",
    "house_cottage_small": "https://www.schemcraft.com/schematics/fantasy-medieval-survival-house",
    "tavern_small": "https://www.schemcraft.com/schematics/grand-medieval-tavern-inn",
    "blacksmith_shop": "https://www.schemcraft.com/schematics/medieval-blacksmith-survival-house",
    "treehouse_oak": "https://www.schemcraft.com/schematics/ultimate-blossom-treehouse-survival-base",
    "castle_small_keep": "https://www.schemcraft.com/schematics/ultimate-fantasy-starter-castle-house",
}


def load_gold_flags() -> dict[str, bool]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    out: dict[str, bool] = {}
    for t in catalog.get("templates") or []:
        tid = str(t.get("id") or "")
        if tid:
            out[tid] = bool(t.get("gold"))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prio",
        choices=("P0", "P1", "P2", "all"),
        default="all",
        help="priority band (default: all open gaps)",
    )
    parser.add_argument(
        "--include-gold",
        action="store_true",
        help="also list rows that are already gold (status column)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="max rows to print (0 = unlimited)",
    )
    args = parser.parse_args(argv)

    gold = load_gold_flags()
    prios = ["P0", "P1", "P2"] if args.prio == "all" else [args.prio]
    rows: list[dict[str, str]] = []
    for prio in prios:
        for tid, ask, notes in GAPS[prio]:
            is_gold = gold.get(tid)
            if is_gold and not args.include_gold:
                continue
            if tid not in gold:
                status = "missing"
            elif is_gold:
                status = "gold"
            else:
                status = "demoted"
            rows.append(
                {
                    "prio": prio,
                    "id": tid,
                    "ask": ask,
                    "status": status,
                    "notes": notes,
                    "starter_url": STARTERS.get(tid, ""),
                }
            )

    if args.limit > 0:
        rows = rows[: args.limit]

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    gold_count = sum(1 for v in gold.values() if v)
    print(f"catalog gold: {gold_count}/{len(gold)}  open gaps shown: {len(rows)}")
    print()
    print(f"{'PRIO':<4}  {'STATUS':<8}  {'ID':<24}  ASK")
    print("-" * 78)
    for row in rows:
        note = f"  # {row['notes']}" if row["notes"] else ""
        starter = f"\n           starter: {row['starter_url']}" if row["starter_url"] else ""
        print(
            f"{row['prio']:<4}  {row['status']:<8}  {row['id']:<24}  {row['ask']}{note}{starter}"
        )

    print()
    print("ingest one (after you pick a licensed .schem URL):")
    print("  make ingest-schem URL='https://…' ID=<catalog_id>")
    print("  make companion-reload")
    print("docs: docs/CURATED_REFILL.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
