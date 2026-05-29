"""FAWE primitive tool definitions for MCP Core v1."""

from __future__ import annotations

from agent.tool_registry import (
    BLOCK_ID,
    COORD,
    PLAYER,
    ToolDefinition,
    Y_COORD,
    _obj,
)

FAWE_DIR = {
    "type": "string",
    "enum": [
        "up",
        "down",
        "north",
        "south",
        "east",
        "west",
        "forward",
        "back",
        "left",
        "right",
        "me",
    ],
    "default": "me",
}

FAWE_TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="select_box",
        description="Set FAWE selection corners at absolute coordinates.",
        parameters=_obj(
            {
                "player": PLAYER,
                "x1": COORD,
                "y1": Y_COORD,
                "z1": COORD,
                "x2": COORD,
                "y2": Y_COORD,
                "z2": COORD,
            },
            ["player", "x1", "y1", "z1", "x2", "y2", "z2"],
        ),
        impl="select_box",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="select_around_player",
        description="Select a box in front of the player from width/depth/height.",
        parameters=_obj(
            {
                "player": PLAYER,
                "width": {"type": "integer", "minimum": 1, "maximum": 128},
                "depth": {"type": "integer", "minimum": 1, "maximum": 128},
                "height": {"type": "integer", "minimum": 1, "maximum": 128},
                "offset_y": {"type": "integer", "minimum": -32, "maximum": 32, "default": 0},
            },
            ["player", "width", "depth", "height"],
        ),
        impl="select_around_player",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="expand_selection",
        description="Expand the current FAWE selection.",
        parameters=_obj(
            {"player": PLAYER, "amount": {"type": "integer", "minimum": 1, "maximum": 256}, "direction": FAWE_DIR},
            ["player", "amount"],
        ),
        impl="expand_selection",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="contract_selection",
        description="Contract the current FAWE selection.",
        parameters=_obj(
            {"player": PLAYER, "amount": {"type": "integer", "minimum": 1, "maximum": 256}, "direction": FAWE_DIR},
            ["player", "amount"],
        ),
        impl="contract_selection",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="selection_size",
        description="Report current FAWE selection dimensions.",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="selection_size",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="set_selection",
        description="Fill selection with a block or pattern (e.g. 50%stone,50%cobblestone).",
        parameters=_obj(
            {"player": PLAYER, "pattern": {"type": "string", "minLength": 1}},
            ["player", "pattern"],
        ),
        impl="set_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="replace_in_selection",
        description="Replace blocks in selection.",
        parameters=_obj(
            {
                "player": PLAYER,
                "from_blocks": {"type": "string", "minLength": 1},
                "to_pattern": {"type": "string", "minLength": 1},
            },
            ["player", "from_blocks", "to_pattern"],
        ),
        impl="replace_in_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="walls_in_selection",
        description="Build walls on selection perimeter.",
        parameters=_obj(
            {"player": PLAYER, "pattern": {"type": "string", "minLength": 1}},
            ["player", "pattern"],
        ),
        impl="walls_in_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="faces_in_selection",
        description="Set outer faces of selection.",
        parameters=_obj(
            {"player": PLAYER, "pattern": {"type": "string", "minLength": 1}},
            ["player", "pattern"],
        ),
        impl="faces_in_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="hollow_selection",
        description="Hollow out selection interior.",
        parameters=_obj(
            {
                "player": PLAYER,
                "thickness": {"type": "integer", "minimum": 1, "maximum": 16, "default": 1},
                "pattern": {"type": "string", "default": "air"},
            },
            ["player"],
        ),
        impl="hollow_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="overlay_selection",
        description="Overlay pattern on top surface of selection.",
        parameters=_obj(
            {"player": PLAYER, "pattern": {"type": "string", "minLength": 1}},
            ["player", "pattern"],
        ),
        impl="overlay_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="stack_selection",
        description="Stack selection copies in a direction.",
        parameters=_obj(
            {
                "player": PLAYER,
                "count": {"type": "integer", "minimum": 1, "maximum": 64},
                "direction": FAWE_DIR,
            },
            ["player", "count"],
        ),
        impl="stack_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="move_selection",
        description="Move selection contents in a direction.",
        parameters=_obj(
            {
                "player": PLAYER,
                "amount": {"type": "integer", "minimum": 1, "maximum": 256},
                "direction": FAWE_DIR,
            },
            ["player", "amount"],
        ),
        impl="move_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="rotate_selection",
        description="Rotate clipboard/selection (yaw 0/90/180/270).",
        parameters=_obj(
            {
                "player": PLAYER,
                "yaw": {"type": "integer", "enum": [0, 90, 180, 270]},
            },
            ["player", "yaw"],
        ),
        impl="rotate_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="flip_selection",
        description="Flip selection along a direction.",
        parameters=_obj(
            {"player": PLAYER, "direction": FAWE_DIR},
            ["player"],
        ),
        impl="flip_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="copy_selection",
        description="Copy current selection to clipboard.",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="copy_selection",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="cut_selection",
        description="Cut current selection to clipboard.",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="cut_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="paste_selection_at_player",
        description="Paste clipboard at player position.",
        parameters=_obj(
            {
                "player": PLAYER,
                "ignore_air": {"type": "boolean", "default": True},
            },
            ["player"],
        ),
        impl="paste_selection_at_player",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="generate_pyramid_at_player",
        description="Generate a pyramid centered on player.",
        parameters=_obj(
            {
                "player": PLAYER,
                "pattern": BLOCK_ID,
                "size": {"type": "integer", "minimum": 1, "maximum": 64},
                "hollow": {"type": "boolean", "default": False},
            },
            ["player", "pattern", "size"],
        ),
        impl="generate_pyramid_at_player",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="generate_forest_at_player",
        description="Generate trees in selection area.",
        parameters=_obj(
            {
                "player": PLAYER,
                "size": {"type": "integer", "minimum": 1, "maximum": 64},
                "tree_type": {"type": "string", "default": "tree"},
                "density": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
            },
            ["player", "size"],
        ),
        impl="generate_forest_at_player",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="smooth_selection",
        description="Smooth terrain in selection.",
        parameters=_obj(
            {
                "player": PLAYER,
                "iterations": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
            },
            ["player"],
        ),
        impl="smooth_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="naturalize_selection",
        description="Naturalize selection (grass/dirt surface).",
        parameters=_obj({"player": PLAYER}, ["player"]),
        impl="naturalize_selection",
        category="fawe",
        risk="medium",
    ),
    ToolDefinition(
        name="undo",
        description="Undo recent FAWE edits for player session.",
        parameters=_obj(
            {
                "player": PLAYER,
                "count": {"type": "integer", "minimum": 1, "maximum": 32, "default": 1},
            },
            ["player"],
        ),
        impl="undo",
        category="fawe",
        risk="low",
    ),
    ToolDefinition(
        name="redo",
        description="Redo undone FAWE edits.",
        parameters=_obj(
            {
                "player": PLAYER,
                "count": {"type": "integer", "minimum": 1, "maximum": 32, "default": 1},
            },
            ["player"],
        ),
        impl="redo",
        category="fawe",
        risk="low",
    ),
)
