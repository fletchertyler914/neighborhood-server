"""Corpus sprint entries (55 -> 100+) — parametric fallbacks until schematics are seeded."""

from __future__ import annotations

from typing import Any

from agent.templates.gold_entries import _SOURCE, _entry


def corpus_sprint_entries() -> list[dict[str, Any]]:
    """45 additional high-frequency templates for hybrid ranker coverage."""

    entries: list[dict[str, Any]] = []

    pen_specs = [
        ("goat_pen_small", "Goat pen", "goat pen", "goat", {"animal": "goat", "count": 3}),
        ("duck_pond_small", "Duck pond", "duck pond", "duck", {"animal": "chicken", "count": 4}),
        ("turkey_pen_small", "Turkey pen", "turkey pen", "chicken", {"animal": "chicken", "count": 4}),
        ("chicken_coop_large", "Large chicken coop", "big chicken coop", "chicken", {"animal": "chicken", "count": 6, "with_roof": True}),
        ("pig_pen_large", "Large pig pen", "big pig pen", "pig", {"animal": "pig", "count": 5, "with_roof": False}),
    ]
    for tid, title, alias, animal_tag, pen_args in pen_specs:
        w = 13 if "large" in tid else 9
        entries.append(
            _entry(
                tid,
                title=title,
                category="farm",
                complexity="common" if "large" in tid else "basic",
                tags=["farm", "pen", animal_tag],
                aliases=[alias, title.lower()],
                footprint=[w, 5, w],
                fallback_tool="build_animal_pen_at_player",
                fallback_args={**pen_args, "width": w - 2, "depth": w - 2},
            )
        )

    crop_specs = [
        ("carrot_farm_small", "Carrot farm", "carrot farm"),
        ("potato_farm_small", "Potato farm", "potato farm"),
        ("pumpkin_farm_small", "Pumpkin farm", "pumpkin farm"),
        ("berry_farm_small", "Berry farm", "berry farm"),
    ]
    for tid, title, alias in crop_specs:
        entries.append(
            _entry(
                tid,
                title=title,
                category="farm",
                complexity="basic",
                tags=["farm", "crop"],
                aliases=[alias],
                footprint=[11, 3, 11],
                fallback_tool="build_platform",
                fallback_args={
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": 9,
                    "depth": 9,
                    "block": "farmland",
                },
            )
        )

    farm_buildings = [
        ("greenhouse_small", "Greenhouse", "greenhouse", [11, 6, 11]),
        ("barn_red_large", "Red barn", "red barn", [15, 8, 13]),
        ("silo_grain", "Grain silo", "silo", [7, 14, 7]),
        ("windmill_small", "Windmill", "windmill", [9, 12, 9]),
    ]
    for tid, title, alias, fp in farm_buildings:
        entries.append(
            _entry(
                tid,
                title=title,
                category="farm",
                complexity="common",
                tags=["farm", "building"],
                aliases=[alias, title.lower()],
                footprint=fp,
                fallback_tool="build_house_at_player",
                fallback_args={"width": fp[0] - 2, "depth": fp[2] - 2, "height": fp[1] - 2},
            )
        )

    shop_specs = [
        ("blacksmith_shop", "Blacksmith", "blacksmith"),
        ("library_small", "Library", "library"),
        ("church_small", "Church", "church"),
        ("market_stall", "Market stall", "market stall"),
    ]
    for tid, title, alias in shop_specs:
        entries.append(
            _entry(
                tid,
                title=title,
                category="house",
                complexity="common",
                tags=["village", "shop", "building"],
                aliases=[alias, title.lower()],
                footprint=[10, 7, 10],
                fallback_tool="build_house_at_player",
                fallback_args={"width": 8, "depth": 8, "height": 6, "wall_block": "stone_bricks"},
            )
        )

    tower_specs = [
        ("wizard_tower", "Wizard tower", "wizard tower", [7, 16, 7], "complex"),
        ("bell_tower", "Bell tower", "bell tower", [5, 20, 5], "common"),
        ("observatory_small", "Observatory", "observatory", [9, 12, 9], "common"),
        ("castle_gate_large", "Castle gate", "castle gate", [11, 10, 7], "complex"),
    ]
    for tid, title, alias, fp, complexity in tower_specs:
        size = max(fp[0], fp[2])
        entries.append(
            _entry(
                tid,
                title=title,
                category="fortress",
                complexity=complexity,
                tags=["fortress", "tower"],
                aliases=[alias, title.lower()],
                footprint=fp,
                fallback_tool="build_castle_at_player",
                fallback_args={"size": max(7, min(size, 21)), "height": min(fp[1] - 2, 14)},
            )
        )

    house_variants = [
        ("beach_hut", "Beach hut", "beach hut", [7, 5, 7]),
        ("igloo_small", "Igloo", "igloo", [8, 5, 8]),
        ("mushroom_house", "Mushroom house", "mushroom house", [8, 7, 8]),
        ("treehouse_oak", "Treehouse", "treehouse", [9, 10, 9]),
        ("modern_house_flat", "Modern house", "modern house", [12, 6, 10]),
        ("apartment_block", "Apartment", "apartment building", [14, 12, 10]),
    ]
    for tid, title, alias, fp in house_variants:
        entries.append(
            _entry(
                tid,
                title=title,
                category="house",
                complexity="common" if fp[1] > 6 else "basic",
                tags=["house", "building"],
                aliases=[alias, title.lower()],
                footprint=fp,
                fallback_tool="build_house_at_player",
                fallback_args={
                    "width": fp[0] - 2,
                    "depth": fp[2] - 2,
                    "height": max(4, fp[1] - 2),
                },
            )
        )

    infra_more = [
        ("bridge_wood_suspension", "Suspension bridge", "suspension bridge", 24, 4, 5),
        ("bridge_rope", "Rope bridge", "rope bridge", 18, 3, 3),
        ("pier_long", "Long pier", "pier", 20, 4, 6),
        ("moat_bridge", "Moat bridge", "moat bridge", 12, 2, 5),
        ("wooden_palisade", "Wooden palisade", "palisade wall", 14, 5, 3),
    ]
    for tid, title, alias, length, height, width in infra_more:
        tool = "build_bridge_at_player" if "bridge" in tid or "pier" in tid else "build_platform"
        if tool == "build_bridge_at_player":
            fb_args: dict[str, Any] = {
                "length": min(length, 48),
                "width": width,
                "block": "oak_planks" if "wood" in tid or "rope" in tid else "stone_bricks",
            }
        else:
            fb_args = {
                "center_x": "${ax}",
                "y": "${ay}",
                "center_z": "${az}",
                "width": length,
                "depth": width,
                "block": "oak_fence" if "palisade" in tid else "cobblestone",
            }
        entries.append(
            _entry(
                tid,
                title=title,
                category="infrastructure",
                complexity="basic",
                tags=["infrastructure", "path"],
                aliases=[alias],
                footprint=[length, height, width],
                fallback_tool=tool,
                fallback_args=fb_args,
            )
        )

    decor_more = [
        ("campground", "Campground", "campground", [13, 2, 13]),
        ("tent_camp", "Tent camp", "tent camp", [11, 4, 11]),
        ("picnic_area", "Picnic area", "picnic area", [9, 2, 9]),
        ("playground_small", "Playground", "playground", [11, 4, 11]),
        ("zen_garden", "Zen garden", "zen garden", [11, 2, 11]),
        ("koi_pond", "Koi pond", "koi pond", [9, 3, 9]),
        ("shrine_small", "Shrine", "shrine", [7, 6, 7]),
        ("graveyard_small", "Graveyard", "graveyard", [15, 3, 15]),
        ("herb_garden", "Herb garden", "herb garden", [8, 2, 8]),
        ("maze_hedge_small", "Hedge maze", "hedge maze", [17, 4, 17]),
    ]
    for tid, title, alias, fp in decor_more:
        entries.append(
            _entry(
                tid,
                title=title,
                category="decoration",
                complexity="basic",
                tags=["decoration", "village"],
                aliases=[alias, title.lower()],
                footprint=fp,
                fallback_tool="build_platform",
                fallback_args={
                    "center_x": "${ax}",
                    "y": "${ay}",
                    "center_z": "${az}",
                    "width": fp[0],
                    "depth": fp[2],
                    "block": "moss_block" if "zen" in tid or "garden" in tid else "grass_block",
                },
            )
        )

    utility_more = [
        ("stable_large", "Large stable", "big horse stable"),
        ("warehouse_small", "Warehouse", "warehouse"),
        ("mill_water", "Water mill", "water mill"),
        ("fishing_hut", "Fishing hut", "fishing hut"),
    ]
    for tid, title, alias in utility_more:
        entries.append(
            _entry(
                tid,
                title=title,
                category="utility",
                complexity="common",
                tags=["utility", "workshop"],
                aliases=[alias, title.lower()],
                footprint=[11, 7, 11],
                fallback_tool="build_house_at_player",
                fallback_args={"width": 9, "depth": 9, "height": 6},
            )
        )

    return entries
