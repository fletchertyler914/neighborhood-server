"""Gold corpus template entries (~50 total with base catalog merge)."""

from __future__ import annotations

from typing import Any

_SOURCE = {
    "source_id": "neighborhood_internal",
    "source_url": "https://github.com/neighborhood-server/templates",
    "source_ref": "gold-v1",
    "license": "CC-BY-4.0",
    "author": "neighborhood",
    "attribution": "Neighborhood Minecraft Server (CC-BY-4.0)",
    "deterministic_seed_version": "1",
}


def _entry(
    tid: str,
    *,
    title: str,
    category: str,
    complexity: str,
    tags: list[str],
    aliases: list[str],
    footprint: list[int],
    fallback_tool: str,
    fallback_args: dict[str, Any],
    follow_up: list[dict[str, Any]] | None = None,
    max_blocks: int | None = None,
    distance: int = 4,
) -> dict[str, Any]:
    fp = footprint
    return {
        "id": tid,
        "title": title,
        "category": category,
        "complexity": complexity,
        "tags": tags,
        "aliases": aliases,
        "schematic": f"{tid}.schem",
        "footprint": fp,
        "max_blocks": max_blocks or max(500, fp[0] * fp[1] * fp[2]),
        "distance_default": distance,
        "follow_up": follow_up or [],
        "fallback": {"tool": fallback_tool, "args": fallback_args},
        **_SOURCE,
    }


def gold_template_entries() -> list[dict[str, Any]]:
    """42 additional gold templates (merge with 8 base = 50)."""

    entries: list[dict[str, Any]] = []

    farm_specs = [
        ("cow_barn_medium", "Cow barn", "cow barn", "cow", {"animal": "cow", "count": 4, "with_roof": True}),
        ("sheep_pen_medium", "Sheep pen", "sheep pen", "sheep", {"animal": "sheep", "count": 4, "with_roof": False}),
        ("bee_apiary_small", "Bee apiary", "bee apiary", "bee", {"animal": "bee", "count": 3, "with_roof": True}),
        ("wheat_farm_small", "Wheat farm", "wheat farm", "farm", {}),
        ("melon_farm_small", "Melon farm", "melon farm", "farm", {}),
        ("sugarcane_farm_small", "Sugarcane farm", "sugar cane farm", "farm", {}),
        ("kelp_farm_small", "Kelp farm", "kelp farm", "farm", {}),
        ("mushroom_farm_dark", "Mushroom farm", "mushroom farm", "farm", {}),
    ]
    for tid, title, alias, tag, pen_args in farm_specs:
        if pen_args:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="farm",
                    complexity="common" if "medium" in tid else "basic",
                    tags=[tag, "farm", "pen"],
                    aliases=[alias],
                    footprint=[11, 5, 11] if "medium" in tid else [9, 4, 9],
                    fallback_tool="build_animal_pen_at_player",
                    fallback_args=pen_args,
                )
            )
        else:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="farm",
                    complexity="basic",
                    tags=[tag, "farm", "crop"],
                    aliases=[alias],
                    footprint=[13, 3, 13],
                    fallback_tool="build_platform",
                    fallback_args={
                        "center_x": "${ax}",
                        "y": "${ay}",
                        "center_z": "${az}",
                        "width": 11,
                        "depth": 11,
                        "block": "farmland",
                    },
                )
            )

    house_specs = [
        ("cottage_medium", "Medium cottage", "medium cottage", 9, 7, 9),
        ("cabin_log", "Log cabin", "log cabin", 8, 6, 8),
        ("cabin_stone", "Stone cabin", "stone cabin", 8, 6, 8),
        ("townhouse_2story", "Townhouse", "townhouse", 10, 8, 10),
        ("desert_house_small", "Desert house", "desert house", 8, 5, 8),
        ("tavern_small", "Tavern", "tavern", 12, 7, 10),
        ("inn_small", "Inn", "inn", 11, 7, 11),
        ("bakery_small", "Bakery", "bakery", 8, 6, 8),
    ]
    for tid, title, alias, w, h, d in house_specs:
        entries.append(
            _entry(
                tid,
                title=title,
                category="house",
                complexity="common" if "medium" in tid or "townhouse" in tid else "basic",
                tags=["house", "building"],
                aliases=[alias, title.lower()],
                footprint=[w, h, d],
                fallback_tool="build_house_at_player",
                fallback_args={"width": w - 2, "depth": d - 2, "height": h - 2},
            )
        )

    fortress_specs = [
        ("watchtower_tall", "Watchtower", "watchtower", [5, 18, 5], "common"),
        ("guard_post", "Guard post", "guard post", [7, 6, 7], "basic"),
        ("wall_segment_stone", "Wall segment", "castle wall", [16, 6, 4], "basic"),
        ("gatehouse", "Gatehouse", "gatehouse", [9, 8, 7], "common"),
        ("fortress_medium", "Fortress", "fortress", [19, 10, 19], "complex"),
        ("lighthouse_short", "Lighthouse", "lighthouse", [6, 14, 6], "common"),
        ("bastion_corner", "Bastion", "bastion", [11, 8, 11], "complex"),
    ]
    for tid, title, alias, fp, complexity in fortress_specs:
        size = max(fp[0], fp[2])
        entries.append(
            _entry(
                tid,
                title=title,
                category="fortress",
                complexity=complexity,
                tags=["fortress", "stone", "defense"],
                aliases=[alias, title.lower()],
                footprint=fp,
                fallback_tool="build_castle_at_player",
                fallback_args={"size": min(size, 25), "height": min(fp[1] - 2, 12)},
                distance=5 if complexity == "complex" else 4,
            )
        )

    infra_specs = [
        ("bridge_stone_long", "Stone bridge", "stone bridge", 32, 3, 5),
        ("road_segment", "Road segment", "road", 16, 1, 5),
        ("archway_stone", "Stone archway", "archway", 5, 8, 5),
        ("dock_small", "Dock", "dock", 14, 3, 8),
        ("rail_segment", "Rail segment", "rail", 24, 2, 3),
    ]
    for tid, title, alias, l, h, w in infra_specs:
        if "bridge" in tid or "road" in tid or "rail" in tid:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="infrastructure",
                    complexity="common" if l > 20 else "basic",
                    tags=["infrastructure", "path"],
                    aliases=[alias],
                    footprint=[l, h, w],
                    fallback_tool="build_bridge_at_player",
                    fallback_args={"length": min(l, 64), "width": w, "block": "stone_bricks"},
                )
            )
        else:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="infrastructure",
                    complexity="basic",
                    tags=["infrastructure"],
                    aliases=[alias],
                    footprint=[l, h, w],
                    fallback_tool="build_platform",
                    fallback_args={
                        "center_x": "${ax}",
                        "y": "${ay}",
                        "center_z": "${az}",
                        "width": l,
                        "depth": w,
                        "block": "oak_planks",
                    },
                )
            )

    decor_specs = [
        ("lamp_post_iron", "Lamp post", "lamp post", [2, 5, 2]),
        ("fountain_small", "Fountain", "fountain", [7, 5, 7]),
        ("garden_plot", "Garden plot", "garden", [9, 3, 9]),
        ("gazebo_oak", "Gazebo", "gazebo", [7, 6, 7]),
        ("statue_pillar", "Statue pillar", "statue", [3, 8, 3]),
        ("flag_pole", "Flag pole", "flag pole", [2, 12, 2]),
        ("plaza_stone", "Stone plaza", "plaza", [11, 1, 11]),
        ("bench_row", "Bench row", "benches", [8, 2, 3]),
    ]
    for tid, title, alias, fp in decor_specs:
        if tid == "garden_plot":
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="farm",
                    complexity="basic",
                    tags=["garden", "farm", "crop", "plants", "decoration"],
                    aliases=[alias, "large garden", "big garden", "flower garden", "veggie garden"],
                    footprint=fp,
                    fallback_tool="build_platform",
                    fallback_args={
                        "center_x": "${ax}",
                        "y": "${ay}",
                        "center_z": "${az}",
                        "width": fp[0],
                        "depth": fp[2],
                        "block": "grass_block",
                    },
                )
            )
            continue
        entries.append(
            _entry(
                tid,
                title=title,
                category="decoration",
                complexity="basic",
                tags=["decoration", "village"],
                aliases=[alias],
                footprint=fp,
                fallback_tool="build_cylinder" if "fountain" in tid or "gazebo" in tid else "build_platform",
                fallback_args=(
                    {"center_x": "${ax}", "y": "${ay}", "center_z": "${az}", "radius": 3, "height": 4, "block": "stone_bricks", "hollow": True}
                    if "fountain" in tid
                    else {
                        "center_x": "${ax}",
                        "y": "${ay}",
                        "center_z": "${az}",
                        "width": fp[0],
                        "depth": fp[2],
                        "block": "stone_bricks",
                    }
                ),
            )
        )

    utility_specs = [
        ("storage_shed", "Storage shed", "storage shed"),
        ("smelter_array", "Smelter array", "smelter"),
        ("brewing_station", "Brewing station", "brewing"),
        ("enchanting_room", "Enchanting room", "enchanting"),
        ("workshop_small", "Workshop", "workshop"),
        ("armory_small", "Armory", "armory"),
    ]
    for tid, title, alias in utility_specs:
        entries.append(
            _entry(
                tid,
                title=title,
                category="utility",
                complexity="common",
                tags=["utility", "workshop"],
                aliases=[alias],
                footprint=[9, 6, 9],
                fallback_tool="build_house_at_player",
                fallback_args={"width": 7, "depth": 7, "height": 5, "wall_block": "cobblestone"},
            )
        )

    nature_specs = [
        ("tree_oak_large", "Large oak tree", "big oak tree"),
        ("tree_dark_oak", "Dark oak tree", "dark oak tree"),
        ("tree_spruce_pine", "Spruce pine", "spruce tree"),
        ("rock_arch", "Rock arch", "rock arch"),
        ("pond_small", "Pond", "pond"),
    ]
    for tid, title, alias in nature_specs:
        if "tree" in tid:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="nature_terrain",
                    complexity="basic",
                    tags=["tree", "nature"],
                    aliases=[alias],
                    footprint=[5, 12, 5],
                    fallback_tool="generate_forest_at_player",
                    fallback_args={"size": 4, "tree_type": "tree", "density": 0.6},
                )
            )
        else:
            entries.append(
                _entry(
                    tid,
                    title=title,
                    category="nature_terrain",
                    complexity="basic",
                    tags=["nature", "terrain"],
                    aliases=[alias],
                    footprint=[9, 4, 9],
                    fallback_tool="build_cylinder",
                    fallback_args={
                        "center_x": "${ax}",
                        "y": "${ay}",
                        "center_z": "${az}",
                        "radius": 4,
                        "height": 2,
                        "block": "water",
                        "hollow": True,
                    },
                )
            )

    return entries
