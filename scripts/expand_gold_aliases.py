#!/usr/bin/env python3
"""Expand kid+adult aliases for gold templates; fix garden/farm catalog rows."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "agent" / "templates" / "catalog.json"

# Extra aliases merged into matching gold ids (deduped, order preserved).
EXTRA: dict[str, list[str]] = {
    "garden_plot": [
        "garden",
        "large garden",
        "big garden",
        "huge garden",
        "nice garden",
        "pretty garden",
        "flower garden",
        "veggie garden",
        "vegetable garden",
        "plant garden",
        "plants",
        "plant bed",
        "garden bed",
        "garden plot",
        "garden patch",
        "my garden",
        "little garden",
        "small garden",
        "starter garden",
        "build a garden",
        "make a garden",
        "plant a garden",
        "grow a garden",
        "garden please",
        "flowers please",
        "flower bed",
        "flower patch",
        "crop garden",
        "allotment",
        "allotment garden",
        "kitchen garden",
        "backyard garden",
        "yard garden",
    ],
    "herb_garden": [
        "herb garden",
        "herbs",
        "spice garden",
        "herb patch",
        "herb bed",
        "little herb garden",
        "my herb garden",
        "garden of herbs",
        "plant herbs",
        "grow herbs",
    ],
    "zen_garden": [
        "zen garden",
        "japanese garden",
        "rock garden",
        "peaceful garden",
        "calm garden",
        "quiet garden",
        "meditation garden",
        "moss garden",
        "little zen garden",
        "my zen garden",
    ],
    "greenhouse_small": [
        "greenhouse",
        "glass greenhouse",
        "glass garden",
        "plant house",
        "hothouse",
        "grow house",
        "little greenhouse",
        "my greenhouse",
        "build a greenhouse",
        "make a greenhouse",
        "glass plant house",
    ],
    "wheat_farm_small": [
        "farm",
        "crop farm",
        "crops",
        "crop field",
        "farmland",
        "farm plot",
        "farm field",
        "wheat farm",
        "wheat field",
        "grain farm",
        "grain field",
        "large farm",
        "big farm",
        "huge farm",
        "my farm",
        "little farm",
        "small farm",
        "starter farm",
        "plant a farm",
        "grow a farm",
        "build a farm",
        "make a farm",
        "farm please",
        "place for crops",
        "crop garden",
    ],
    "carrot_farm_small": [
        "carrot farm",
        "carrot garden",
        "carrot field",
        "carrot patch",
        "carrots",
        "farm for carrots",
        "grow carrots",
        "plant carrots",
        "my carrot farm",
        "little carrot farm",
    ],
    "potato_farm_small": [
        "potato farm",
        "potato garden",
        "potato field",
        "potato patch",
        "potatoes",
        "farm for potatoes",
        "grow potatoes",
        "plant potatoes",
        "my potato farm",
        "little potato farm",
    ],
    "berry_farm_small": [
        "berry farm",
        "berry garden",
        "berry patch",
        "berries",
        "sweet berry farm",
        "grow berries",
        "plant berries",
        "my berry farm",
        "little berry farm",
    ],
    "pumpkin_farm_small": [
        "pumpkin farm",
        "pumpkin patch",
        "pumpkin garden",
        "pumpkins",
        "grow pumpkins",
        "plant pumpkins",
        "my pumpkin farm",
        "little pumpkin farm",
        "halloween farm",
    ],
    "melon_farm_small": [
        "melon farm",
        "melon patch",
        "melon garden",
        "melons",
        "grow melons",
        "plant melons",
        "my melon farm",
        "little melon farm",
    ],
    "sugarcane_farm_small": [
        "sugarcane farm",
        "sugar cane farm",
        "reed farm",
        "cane farm",
        "sugarcane",
        "sugar cane",
        "grow sugarcane",
        "plant sugarcane",
        "my sugarcane farm",
    ],
    "barn_red_large": [
        "barn",
        "red barn",
        "big barn",
        "large barn",
        "farm barn",
        "my barn",
        "little barn",
        "barn house",
        "barn building",
    ],
    "silo_grain": [
        "silo",
        "grain silo",
        "farm silo",
        "wheat silo",
        "my silo",
        "little silo",
        "grain tower",
    ],
    "windmill_small": [
        "windmill",
        "farm windmill",
        "little windmill",
        "my windmill",
        "grain mill",
        "wind mill",
    ],
    "chicken_coop_small": [
        "chicken coop",
        "chicken house",
        "hen house",
        "chick house",
        "house for chickens",
        "home for chickens",
        "place for chickens",
        "chicken barn",
        "coop for chickens",
        "my chicken coop",
        "little chicken coop",
        "chicks",
    ],
    "cow_barn_medium": [
        "cow barn",
        "cow pen",
        "cow house",
        "house for cows",
        "home for cows",
        "place for cows",
        "cattle barn",
        "my cow barn",
        "little cow barn",
    ],
    "pig_pen_small": [
        "pig pen",
        "pig house",
        "pig sty",
        "house for pigs",
        "home for pigs",
        "place for pigs",
        "my pig pen",
        "little pig pen",
    ],
    "sheep_pen_medium": [
        "sheep pen",
        "sheep house",
        "house for sheep",
        "home for sheep",
        "place for sheep",
        "my sheep pen",
        "little sheep pen",
    ],
    "horse_stable_small": [
        "horse stable",
        "stable",
        "horse barn",
        "house for horses",
        "home for horses",
        "place for horses",
        "my stable",
        "little stable",
    ],
    "bee_apiary_small": [
        "bee house",
        "apiary",
        "bee farm",
        "beehive house",
        "house for bees",
        "home for bees",
        "place for bees",
        "my bee house",
        "little bee farm",
    ],
    "castle_small_keep": [
        "castle",
        "little castle",
        "small castle",
        "my castle",
        "keep",
        "fort",
        "fortress",
        "stone castle",
        "medieval castle",
        "castle keep",
    ],
    "house_cottage_small": [
        "cottage",
        "little house",
        "small house",
        "starter house",
        "cozy house",
        "cozy cottage",
        "my cottage",
        "little cottage",
        "small cottage",
    ],
    "bridge_oak_short": [
        "bridge",
        "wooden bridge",
        "oak bridge",
        "wood bridge",
        "little bridge",
        "small bridge",
        "my bridge",
        "bridge please",
    ],
    "watchtower_tall": [
        "watchtower",
        "watch tower",
        "lookout tower",
        "guard tower",
        "tall tower",
        "my watchtower",
        "little watchtower",
    ],
    "fountain_small": [
        "fountain",
        "water fountain",
        "little fountain",
        "my fountain",
        "town fountain",
        "plaza fountain",
    ],
    "well_village": [
        "well",
        "wishing well",
        "village well",
        "water well",
        "my well",
        "little well",
    ],
    "tree_oak_large": [
        "oak tree",
        "big oak tree",
        "large oak tree",
        "big tree",
        "large tree",
        "tree",
        "my oak tree",
    ],
    "treehouse_oak": [
        "treehouse",
        "tree house",
        "oak treehouse",
        "my treehouse",
        "little treehouse",
    ],
    "lighthouse_short": [
        "lighthouse",
        "light house",
        "beacon tower",
        "my lighthouse",
        "little lighthouse",
    ],
    "cabin_log": [
        "log cabin",
        "cabin",
        "wood cabin",
        "wooden cabin",
        "my cabin",
        "little cabin",
        "forest cabin",
    ],
    "cottage_medium": [
        "medium cottage",
        "bigger cottage",
        "large cottage",
        "family cottage",
        "my medium cottage",
    ],
    "plaza_stone": [
        "plaza",
        "stone plaza",
        "town square",
        "courtyard plaza",
        "stone square",
        "my plaza",
    ],
    "gazebo_oak": [
        "gazebo",
        "garden gazebo",
        "oak gazebo",
        "my gazebo",
        "little gazebo",
        "gazebo in the garden",
    ],
    "picnic_area": [
        "picnic area",
        "picnic spot",
        "picnic place",
        "my picnic area",
        "little picnic area",
    ],
    "playground_small": [
        "playground",
        "play area",
        "kids playground",
        "play place",
        "my playground",
        "little playground",
    ],
    "pond_small": [
        "pond",
        "little pond",
        "small pond",
        "water pond",
        "my pond",
        "garden pond",
    ],
    "koi_pond": [
        "koi pond",
        "fish pond",
        "my koi pond",
        "little koi pond",
        "japanese pond",
    ],
    "duck_pond_small": [
        "duck pond",
        "pond for ducks",
        "my duck pond",
        "little duck pond",
    ],
    "campground": [
        "campground",
        "camp site",
        "camping spot",
        "my campground",
        "little campground",
    ],
    "tent_camp": [
        "tent",
        "tent camp",
        "camp tent",
        "my tent",
        "little tent",
    ],
}

# Generic paraphrase patterns applied to every gold template from title/id.
GENERIC_SUFFIXES = [
    "please",
    "for me",
    "over there",
    "right here",
    "nearby",
]


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = " ".join(item.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _generic_for(title: str, tid: str) -> list[str]:
    base = title.lower().strip()
    words = tid.replace("_", " ")
    aliases = [
        base,
        words,
        f"little {base}",
        f"small {base}",
        f"my {base}",
        f"build a {base}",
        f"make a {base}",
        f"build me a {base}",
        f"make me a {base}",
        f"can you build a {base}",
        f"please build a {base}",
        f"i want a {base}",
        f"i need a {base}",
    ]
    for suffix in GENERIC_SUFFIXES:
        aliases.append(f"{base} {suffix}")
    return aliases


def main() -> None:
    data = json.loads(CATALOG.read_text())
    templates = data["templates"]
    before_alias = sum(len(t.get("aliases") or []) for t in templates if t.get("gold"))
    gold_before = sum(1 for t in templates if t.get("gold"))

    # Promote strong farm/garden-adjacent schems.
    promote = {
        "kelp_farm_small",
        "mushroom_farm_dark",
        "maze_hedge_small",
        "chicken_coop_large",
        "pig_pen_large",
    }
    for t in templates:
        if t["id"] in promote:
            t["gold"] = True

    for t in templates:
        tid = t["id"]
        aliases = list(t.get("aliases") or [])
        if t.get("gold") or tid in EXTRA:
            aliases.extend(_generic_for(str(t.get("title") or tid), tid))
            aliases.extend(EXTRA.get(tid, []))
        t["aliases"] = _uniq(aliases)

        # Fix garden/farm metadata + seed fallbacks so reseed stays planty.
        if tid == "garden_plot":
            t["category"] = "farm"
            t["tags"] = _uniq(["garden", "farm", "crop", "plants", "decoration"])
            t["complexity"] = "basic"
            t["footprint"] = [9, 3, 9]
            t["fallback"] = {
                "tool": "build_platform",
                "args": {
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": 9,
                    "depth": 9,
                    "block": "grass_block",
                },
            }
        elif tid == "herb_garden":
            t["category"] = "farm"
            t["tags"] = _uniq(["garden", "farm", "plants", "decoration"])
            t["footprint"] = [8, 3, 8]
            t["fallback"] = {
                "tool": "build_platform",
                "args": {
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": 8,
                    "depth": 8,
                    "block": "podzol",
                },
            }
        elif tid == "zen_garden":
            t["tags"] = _uniq(["garden", "decoration", "village", "moss"])
            t["footprint"] = [11, 3, 11]
            t["fallback"] = {
                "tool": "build_platform",
                "args": {
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": 11,
                    "depth": 11,
                    "block": "moss_block",
                },
            }
        elif tid.endswith("_farm_small") or tid in {
            "wheat_farm_small",
            "carrot_farm_small",
            "potato_farm_small",
            "berry_farm_small",
            "pumpkin_farm_small",
            "melon_farm_small",
            "sugarcane_farm_small",
        }:
            t["tags"] = _uniq(list(t.get("tags") or []) + ["farm", "crop", "plants"])
            t["footprint"] = [11, 3, 11]
            t["fallback"] = {
                "tool": "build_platform",
                "args": {
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": 11,
                    "depth": 11,
                    "block": "farmland",
                },
            }

        # Strip bare "farm" from non-default farms so wheat_farm_small wins.
        if tid != "wheat_farm_small" and t.get("category") == "farm":
            t["aliases"] = [a for a in t["aliases"] if a not in {"farm", "crops", "farmland"}]

    after_alias = sum(len(t.get("aliases") or []) for t in templates if t.get("gold"))
    gold_after = sum(1 for t in templates if t.get("gold"))
    CATALOG.write_text(json.dumps(data, indent=2) + "\n")
    print(
        f"gold {gold_before}→{gold_after}; "
        f"gold aliases {before_alias}→{after_alias} "
        f"(+{after_alias - before_alias})"
    )


if __name__ == "__main__":
    main()
