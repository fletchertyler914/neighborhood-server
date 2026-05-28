"""Single source of truth for agent tool contracts.

All tool surfaces (OpenAI schemas, dispatch map, MCP exposure) derive from
``TOOL_DEFINITIONS``. Bump ``TOOLS_VERSION`` when changing parameters or
semantics so eval baselines and training exports can track contract drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

TOOLS_VERSION = "2.8.0"
TOOLS_SCHEMA_VERSION = 1

# Shared JSON-schema fragments
PLAYER = {"type": "string", "minLength": 1}
COORD = {"type": "integer", "minimum": -30000000, "maximum": 30000000}
Y_COORD = {"type": "integer", "minimum": -64, "maximum": 320}
BLOCK_ID = {"type": "string", "minLength": 1, "description": "Minecraft block id, e.g. stone_bricks"}


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class ToolDefinition:
    """Declarative tool contract."""

    name: str
    description: str
    parameters: dict[str, Any]
    impl: str  # attribute name on agent.tools module
    category: str = "general"
    risk: str = "low"  # low | medium | high | destructive
    mcp: bool = True
    orchestrator: bool = True


def to_openai_schema(defn: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": defn.name,
            "description": defn.description,
            "parameters": defn.parameters,
        },
    }


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="server_status",
        description="Get container/RCON status and current online players.",
        parameters=_obj({}),
        impl="server_status",
        category="status",
    ),
    ToolDefinition(
        name="preflight",
        description="Check server health and list online players before acting.",
        parameters=_obj({}),
        impl="preflight",
        category="status",
    ),
    ToolDefinition(
        name="list_players",
        description="List online players.",
        parameters=_obj({}),
        impl="list_players",
        category="status",
    ),
    ToolDefinition(
        name="get_player_position",
        description="Get player/entity position coordinates.",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="get_player_position",
        category="player",
    ),
    ToolDefinition(
        name="get_player_dimension",
        description="Get player/entity current dimension (overworld/nether/end).",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="get_player_dimension",
        category="player",
    ),
    ToolDefinition(
        name="backup_now",
        description="Trigger an immediate backup (recommended before destructive operations).",
        parameters=_obj({}),
        impl="backup_now",
        category="safety",
        risk="medium",
    ),
    ToolDefinition(
        name="fill_box",
        description="Fill a cuboid region (guarded by block-volume limits).",
        parameters=_obj(
            {
                "x1": COORD,
                "y1": Y_COORD,
                "z1": COORD,
                "x2": COORD,
                "y2": Y_COORD,
                "z2": COORD,
                "block": BLOCK_ID,
                "mode": {
                    "type": "string",
                    "enum": ["replace", "hollow", "outline", "destroy", "keep"],
                    "default": "replace",
                },
            },
            ["x1", "y1", "z1", "x2", "y2", "z2", "block"],
        ),
        impl="fill_box",
        category="build",
        risk="medium",
    ),
    ToolDefinition(
        name="clear_box",
        description="Clear a cuboid region to air.",
        parameters=_obj(
            {
                "x1": COORD,
                "y1": Y_COORD,
                "z1": COORD,
                "x2": COORD,
                "y2": Y_COORD,
                "z2": COORD,
            },
            ["x1", "y1", "z1", "x2", "y2", "z2"],
        ),
        impl="clear_box",
        category="build",
        risk="high",
    ),
    ToolDefinition(
        name="build_platform",
        description="Build a centered rectangular platform at fixed y.",
        parameters=_obj(
            {
                "center_x": COORD,
                "y": Y_COORD,
                "center_z": COORD,
                "width": {"type": "integer", "minimum": 1, "maximum": 512},
                "depth": {"type": "integer", "minimum": 1, "maximum": 512},
                "block": BLOCK_ID,
            },
            ["center_x", "y", "center_z", "width", "depth", "block"],
        ),
        impl="build_platform",
        category="build",
    ),
    ToolDefinition(
        name="build_sphere",
        description="Build a sphere or hollow sphere (radius 1..24).",
        parameters=_obj(
            {
                "center_x": COORD,
                "center_y": Y_COORD,
                "center_z": COORD,
                "radius": {"type": "integer", "minimum": 1, "maximum": 24},
                "block": BLOCK_ID,
                "hollow": {"type": "boolean", "default": True},
            },
            ["center_x", "center_y", "center_z", "radius", "block"],
        ),
        impl="build_sphere",
        category="build",
    ),
    ToolDefinition(
        name="build_cylinder",
        description="Build a vertical cylinder (solid or hollow).",
        parameters=_obj(
            {
                "center_x": COORD,
                "y": Y_COORD,
                "center_z": COORD,
                "radius": {"type": "integer", "minimum": 1, "maximum": 32},
                "height": {"type": "integer", "minimum": 1, "maximum": 128},
                "block": BLOCK_ID,
                "hollow": {"type": "boolean", "default": False},
            },
            ["center_x", "y", "center_z", "radius", "height", "block"],
        ),
        impl="build_cylinder",
        category="build",
    ),
    ToolDefinition(
        name="build_house",
        description=(
            "Build a small rectangular house with walls, roof, a functional door, "
            "and two front windows. Prefer this for prompts asking for a house, "
            "cabin, door, or windows."
        ),
        parameters=_obj(
            {
                "center_x": COORD,
                "y": Y_COORD,
                "center_z": COORD,
                "width": {"type": "integer", "minimum": 5, "maximum": 21, "default": 7},
                "depth": {"type": "integer", "minimum": 5, "maximum": 21, "default": 7},
                "height": {"type": "integer", "minimum": 4, "maximum": 12, "default": 5},
                "wall_block": {"type": "string", "default": "oak_planks"},
                "roof_block": {"type": "string", "default": "oak_slab"},
                "window_block": {"type": "string", "default": "glass_pane"},
                "door_block": {"type": "string", "default": "oak_door"},
            },
            ["center_x", "y", "center_z"],
        ),
        impl="build_house",
        category="build",
    ),
    ToolDefinition(
        name="build_house_at_player",
        description=(
            "Build a house in front of the player with the door facing the player. "
            "Use this for prompts like 'build me a house in front of me', "
            "'build a cabin here', or 'build a sand fort with a door in front of me'."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "width": {"type": "integer", "minimum": 5, "maximum": 21, "default": 7},
                "depth": {"type": "integer", "minimum": 5, "maximum": 21, "default": 7},
                "height": {"type": "integer", "minimum": 4, "maximum": 16, "default": 5},
                "distance": {"type": "integer", "minimum": 1, "maximum": 12, "default": 3},
                "wall_block": {"type": "string", "default": "oak_planks"},
                "roof_block": {"type": "string", "default": "oak_slab"},
                "window_block": {"type": "string", "default": "glass_pane"},
                "door_block": {"type": "string", "default": "oak_door"},
                "floor_block": {"type": ["string", "null"], "default": None},
                "stair_block": {"type": ["string", "null"], "default": None},
                "add_floors": {"type": "boolean", "default": True},
            },
            ["player"],
        ),
        impl="build_house_at_player",
        category="build",
    ),
    ToolDefinition(
        name="build_castle_at_player",
        description=(
            "Build a small castle in front of the player with hollow walls, "
            "four corner towers, crenelations on top, and an open doorway "
            "facing the player. Use this for ANY 'build a castle', 'castle "
            "fort', 'fortress', or 'keep' prompt. DO NOT use build_cylinder "
            "or build_sphere for castles — those produce solid pillars or "
            "blobs."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "size": {"type": "integer", "minimum": 7, "maximum": 31, "default": 15},
                "height": {"type": "integer", "minimum": 4, "maximum": 24, "default": 6},
                "tower_height": {"type": "integer", "minimum": 5, "maximum": 36, "default": 10},
                "tower_size": {"type": "integer", "minimum": 2, "maximum": 5, "default": 3},
                "distance": {"type": "integer", "minimum": 1, "maximum": 12, "default": 3},
                "wall_block": {"type": "string", "default": "stone_bricks"},
                "floor_block": {"type": "string", "default": "stone_bricks"},
                "roof_block": {"type": "string", "default": "stone_brick_slab"},
                "door_block": {"type": "string", "default": "oak_door"},
            },
            ["player"],
        ),
        impl="build_castle_at_player",
        category="build",
    ),
    ToolDefinition(
        name="build_animal_pen_at_player",
        description=(
            "Build a fenced animal pen in front of the player and summon "
            "the requested mob inside. Use this for ANY 'chicken coop', "
            "'pig pen', 'cow pen', 'sheep pen', 'rabbit hutch', "
            "'animal enclosure', 'fenced area for chickens', 'horse "
            "stable', 'corral', or similar prompt. Set with_roof=true for "
            "coop / barn / hutch / stable prompts (anything covered); "
            "leave false for an open-air pen / paddock / corral. DO NOT "
            "call build_house with wall_block=pumpkin to fake a coop."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "animal": {
                    "type": "string",
                    "default": "chicken",
                    "description": (
                        "Mob id (chicken, pig, cow, sheep, rabbit, horse, "
                        "goat, bee, llama, parrot, …). Plurals accepted."
                    ),
                },
                "count": {"type": "integer", "minimum": 1, "maximum": 16, "default": 4},
                "width": {"type": "integer", "minimum": 3, "maximum": 21, "default": 7},
                "depth": {"type": "integer", "minimum": 3, "maximum": 21, "default": 7},
                "distance": {"type": "integer", "minimum": 1, "maximum": 12, "default": 3},
                "fence_block": {"type": "string", "default": "oak_fence"},
                "gate_block": {"type": "string", "default": "oak_fence_gate"},
                "floor_block": {"type": "string", "default": "grass_block"},
                "with_roof": {"type": "boolean", "default": False},
                "roof_block": {"type": "string", "default": "oak_slab"},
                "wall_block": {"type": "string", "default": "oak_planks"},
                "wall_height": {"type": "integer", "minimum": 2, "maximum": 6, "default": 3},
            },
            ["player"],
        ),
        impl="build_animal_pen_at_player",
        category="build",
    ),
    ToolDefinition(
        name="search_templates",
        description=(
            "Rank build templates for a natural-language query. Returns top "
            "candidates, confidence (high/medium/low), and optional "
            "disambiguation text. Use before paste_template_at_player when the "
            "player's request is vague ('build something cool', 'a farm thing'). "
            "paste_template_at_player also accepts free text and runs the same "
            "ranker internally."
        ),
        parameters=_obj(
            {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Natural language, e.g. 'small chicken coop', "
                        "'stone fortress', 'wooden bridge'."
                    ),
                },
                "category": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Optional category filter (farm, house, …).",
                },
                "intent_family": {
                    "type": "string",
                    "default": "",
                    "description": (
                        "Optional routing hint: farm_pen, castle, bridge, house."
                    ),
                },
            },
            ["query"],
        ),
        impl="search_templates",
        category="templates",
    ),
    ToolDefinition(
        name="list_templates",
        description=(
            "List curated build templates (schematics) available for paste. "
            "Prefer search_templates for vague natural-language requests. "
            "paste_template_at_player accepts free text and resolves via the "
            "hybrid ranker."
        ),
        parameters=_obj(
            {
                "category": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Filter by category (farm, house, fortress, …).",
                },
                "tags": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "default": None,
                    "description": "Filter templates that include any of these tags.",
                },
            },
            [],
        ),
        impl="list_templates",
        category="templates",
    ),
    ToolDefinition(
        name="paste_template_at_player",
        description=(
            "Build a named structure in front of the player. PRIMARY tool for "
            "natural-language build requests: chicken coop, castle, cottage, "
            "barn, pig pen, rabbit hutch, horse stable, watchtower, fountain, "
            "well, bridge, lighthouse, gazebo, tree, garden, etc. "
            "`template` accepts either a catalog id OR a free-text description "
            "(e.g. 'small chicken coop', 'stone fortress', 'wooden bridge') "
            "and the server resolves it to the best match. Prefer this over "
            "build_house / build_castle / build_animal_pen_at_player for "
            "natural builder-quality results."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "template_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Template id OR a free-text description. Examples: "
                        "'chicken coop', 'small castle', 'pig pen', "
                        "'watchtower', 'rabbit hutch', 'wooden bridge'. "
                        "The server fuzzy-matches and picks the best fit."
                    ),
                },
                "distance": {
                    "type": ["integer", "null"],
                    "default": None,
                    "description": "Blocks in front of player to place anchor.",
                },
                "rotation": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 270,
                    "default": 0,
                    "description": "Paste rotation in degrees (0/90/180/270).",
                },
                "mirror": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Optional mirror axis: x, z, or xz.",
                },
                "adapt_palette": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, run a simple //replace palette pass after paste.",
                },
            },
            ["player", "template_id"],
        ),
        impl="paste_template_at_player",
        category="templates",
        risk="medium",
    ),
    ToolDefinition(
        name="create_template_from_selection",
        description=(
            "Publish the player's current FAWE selection as a reusable template. "
            "Player must have //pos1 and //pos2 set (wand). Saves "
            "//schem save neighborhood/<template_id> and registers catalog metadata. "
            "Use overwrite=true to replace an existing template."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "template_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "New or existing template id (snake_case).",
                },
                "overwrite": {"type": "boolean", "default": False},
                "tags": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "default": None,
                },
            },
            ["player", "template_id"],
        ),
        impl="create_template_from_selection",
        category="templates",
        risk="medium",
        mcp=False,
    ),
    ToolDefinition(
        name="build_bridge_at_player",
        description=(
            "Build a horizontal bridge straight in front of the player. "
            "Use this for any 'build a bridge', 'build a walkway across the water', "
            "or 'plank a path to that island' prompt. Forward direction is read "
            "from the player's facing — DO NOT pass absolute coordinates."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "length": {"type": "integer", "minimum": 2, "maximum": 128, "default": 24},
                "width": {"type": "integer", "minimum": 1, "maximum": 8, "default": 2},
                "block": {"type": "string", "default": "oak_planks"},
                "distance": {"type": "integer", "minimum": 0, "maximum": 8, "default": 1},
                "rail_block": {"type": ["string", "null"], "default": None},
                "rail_height": {"type": "integer", "minimum": 0, "maximum": 4, "default": 1},
                "support_block": {"type": ["string", "null"], "default": None},
                "support_every": {"type": "integer", "minimum": 2, "maximum": 32, "default": 6},
                "support_drop": {"type": "integer", "minimum": 0, "maximum": 24, "default": 6},
                "add_supports": {"type": "boolean", "default": True},
                "add_rails": {"type": "boolean", "default": True},
            },
            ["player"],
        ),
        impl="build_bridge_at_player",
        category="build",
    ),
    ToolDefinition(
        name="build_wall_at_player",
        description=(
            "Build a flat wall directly in front of the player, perpendicular to "
            "their facing. Use for 'block off this area in front of me' style prompts."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "length": {"type": "integer", "minimum": 2, "maximum": 64, "default": 16},
                "height": {"type": "integer", "minimum": 1, "maximum": 32, "default": 4},
                "block": {"type": "string", "default": "stone_bricks"},
                "distance": {"type": "integer", "minimum": 0, "maximum": 8, "default": 2},
            },
            ["player"],
        ),
        impl="build_wall_at_player",
        category="build",
    ),
    ToolDefinition(
        name="build_spiral_staircase",
        description="Build a spiral staircase around a central pillar.",
        parameters=_obj(
            {
                "center_x": COORD,
                "y": Y_COORD,
                "center_z": COORD,
                "height": {"type": "integer", "minimum": 2, "maximum": 128},
                "radius": {"type": "integer", "minimum": 2, "maximum": 12},
                "block": {"type": "string", "default": "smooth_stone"},
            },
            ["center_x", "y", "center_z", "height", "radius"],
        ),
        impl="build_spiral_staircase",
        category="build",
    ),
    ToolDefinition(
        name="fawe_as_player",
        description=(
            "Run a FAWE command as the player. Command should be a WorldEdit verb "
            "such as '//sphere glass 10' or '//set stone'."
        ),
        parameters=_obj(
            {"player": PLAYER, "command": {"type": "string", "minLength": 1}},
            ["player", "command"],
        ),
        impl="fawe_as_player",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="fawe_sphere_at_player",
        description="Build a FAWE sphere centered on player.",
        parameters=_obj(
            {
                "player": PLAYER,
                "block": BLOCK_ID,
                "radius": {"type": "integer", "minimum": 1, "maximum": 64},
            },
            ["player", "block", "radius"],
        ),
        impl="fawe_sphere_at_player",
        category="fawe",
    ),
    ToolDefinition(
        name="fawe_cyl_at_player",
        description=(
            "Build a FAWE cylinder centered on player. "
            "Set hollow=true for an open-top ring/fort wall (uses //cyl -h)."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "block": BLOCK_ID,
                "radius": {"type": "integer", "minimum": 1, "maximum": 64},
                "height": {"type": "integer", "minimum": 1, "maximum": 256},
                "hollow": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, only the outer ring is built (//cyl -h).",
                },
            },
            ["player", "block", "radius", "height"],
        ),
        impl="fawe_cyl_at_player",
        category="fawe",
    ),
    ToolDefinition(
        name="mine_shaft_at_player",
        description=(
            "Drill a downward shaft beneath the player using fill. "
            "For prompts like '1 block forward', pass forward_offset=1 "
            "(positive means ahead, negative means behind)."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 256,
                    "description": "Vertical blocks to clear.",
                },
                "radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "description": "0=1x1 shaft, 1=3x3 shaft, etc.",
                },
                "forward_offset": {
                    "type": "integer",
                    "minimum": -16,
                    "maximum": 16,
                    "description": "Positive=in front of player, negative=behind.",
                },
            },
            ["player"],
        ),
        impl="mine_shaft_at_player",
        category="mining",
    ),
    ToolDefinition(
        name="op_player",
        description="Grant operator permissions to a player.",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="op_player",
        category="admin",
        risk="high",
    ),
    ToolDefinition(
        name="give_item",
        description=(
            "Give a vanilla item to a player using /give. Use this for ANY "
            "'give me a <thing>' prompt (pickaxe, sword, blocks, food, "
            "elytra, etc). Do NOT use give_haste for items, and do NOT use "
            "fawe_as_player //give (FAWE has no //give). The tool understands "
            "common aliases: pickaxe → diamond_pickaxe, sword → diamond_sword, "
            "armor → diamond_chestplate."
        ),
        parameters=_obj(
            {
                "player": PLAYER,
                "item": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Minecraft item id (diamond_pickaxe, oak_planks, etc).",
                },
                "count": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                "components": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": (
                        "Optional 1.20.5+ item components string, including "
                        "the brackets, e.g. '[minecraft:enchantments={...}]'."
                    ),
                },
            },
            ["player", "item"],
        ),
        impl="give_item",
        category="player",
        risk="medium",
    ),
    ToolDefinition(
        name="summon_entity",
        description=(
            "Summon vanilla mobs at absolute coordinates using /summon. "
            "Use this for prompts like 'spawn 4 chickens here', 'summon a "
            "villager next to me', or 'drop a cow at 100 64 200'. For a "
            "fenced area with animals (chicken coop, pig pen, etc.), use "
            "build_animal_pen_at_player instead. Boss entities (wither, "
            "ender_dragon, warden, elder_guardian) are refused."
        ),
        parameters=_obj(
            {
                "entity": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Mob id (chicken, cow, villager, axolotl, …). "
                        "Plurals like 'chickens' are normalized."
                    ),
                },
                "x": COORD,
                "y": Y_COORD,
                "z": COORD,
                "count": {"type": "integer", "minimum": 1, "maximum": 32, "default": 1},
                "nbt": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Optional vanilla NBT tail, e.g. '{NoAI:1b}'.",
                },
            },
            ["entity", "x", "y", "z"],
        ),
        impl="summon_entity",
        category="world",
        risk="medium",
    ),
    ToolDefinition(
        name="give_haste",
        description="Grant haste effect for faster mining.",
        parameters=_obj(
            {
                "player": PLAYER,
                "duration_sec": {"type": "integer", "minimum": 1, "maximum": 7200, "default": 600},
                "amplifier": {"type": "integer", "minimum": 0, "maximum": 4, "default": 2},
            },
            ["player"],
        ),
        impl="give_haste",
        category="effects",
    ),
    ToolDefinition(
        name="teleport_player",
        description="Teleport player to absolute coordinates.",
        parameters=_obj(
            {"player": PLAYER, "x": COORD, "y": Y_COORD, "z": COORD},
            ["player", "x", "y", "z"],
        ),
        impl="teleport_player",
        category="player",
        risk="medium",
    ),
    ToolDefinition(
        name="set_gamemode",
        description="Set a player's gamemode.",
        parameters=_obj(
            {
                "player": PLAYER,
                "mode": {
                    "type": "string",
                    "enum": ["survival", "creative", "adventure", "spectator"],
                },
            },
            ["player", "mode"],
        ),
        impl="set_gamemode",
        category="admin",
    ),
    ToolDefinition(
        name="say",
        description="Broadcast a server chat message.",
        parameters=_obj(
            {"message": {"type": "string", "minLength": 1, "maxLength": 256}},
            ["message"],
        ),
        impl="say",
        category="chat",
    ),
    ToolDefinition(
        name="set_time",
        description=(
            "Set world time. Canonical: day, night, noon, midnight. "
            "Aliases: morning/dawn/sunrise→day, afternoon→noon, "
            "dusk/sunset/evening→night."
        ),
        parameters=_obj(
            {
                "value": {
                    "type": "string",
                    "enum": [
                        "day",
                        "night",
                        "noon",
                        "midnight",
                        "morning",
                        "dawn",
                        "sunrise",
                        "afternoon",
                        "dusk",
                        "sunset",
                        "evening",
                    ],
                }
            },
            ["value"],
        ),
        impl="set_time",
        category="world",
    ),
    ToolDefinition(
        name="set_weather",
        description="Set weather. Aliases: sun/sunny→clear, storm→thunder.",
        parameters=_obj(
            {
                "weather": {
                    "type": "string",
                    "enum": ["clear", "rain", "thunder", "sun", "sunny", "storm"],
                }
            },
            ["weather"],
        ),
        impl="set_weather",
        category="world",
    ),
    ToolDefinition(
        name="run_command",
        description="Raw RCON escape hatch. Prefer typed tools when available.",
        parameters=_obj({"command": {"type": "string", "minLength": 1}}, ["command"]),
        impl="run_command",
        category="escape",
        risk="high",
        mcp=True,
    ),
)

from agent.tool_registry_fawe import FAWE_TOOL_DEFINITIONS  # noqa: E402

TOOL_DEFINITIONS = TOOL_DEFINITIONS + FAWE_TOOL_DEFINITIONS

TOOL_DEFINITIONS_BY_NAME: dict[str, ToolDefinition] = {d.name: d for d in TOOL_DEFINITIONS}


def build_openai_schemas(*, orchestrator_only: bool = True) -> list[dict[str, Any]]:
    defs = [
        d
        for d in TOOL_DEFINITIONS
        if (not orchestrator_only or d.orchestrator)
    ]
    return [to_openai_schema(d) for d in defs]


def build_dispatch(module: Any) -> dict[str, Callable[..., Any]]:
    """Wire registry impl names to callables on ``agent.tools`` module."""

    dispatch: dict[str, Callable[..., Any]] = {}
    for defn in TOOL_DEFINITIONS:
        fn = getattr(module, defn.impl, None)
        if fn is None or not callable(fn):
            raise RuntimeError(f"tool {defn.name}: missing impl {defn.impl!r} on tools module")
        dispatch[defn.name] = fn
    return dispatch


def mcp_tool_names() -> list[str]:
    return [d.name for d in TOOL_DEFINITIONS if d.mcp]


def validate_registry() -> None:
    names = [d.name for d in TOOL_DEFINITIONS]
    if len(names) != len(set(names)):
        dupes = [n for n in names if names.count(n) > 1]
        raise RuntimeError(f"duplicate tool names in TOOL_DEFINITIONS: {sorted(set(dupes))}")
    from agent import tools as tools_mod

    for defn in TOOL_DEFINITIONS:
        fn = getattr(tools_mod, defn.impl, None)
        if fn is None or not callable(fn):
            raise RuntimeError(f"tool {defn.name}: missing impl {defn.impl!r} on tools module")
