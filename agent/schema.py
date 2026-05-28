"""OpenAI-compatible tool schemas for LLM orchestration."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "preflight",
            "description": "Check server health and online players before acting.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_players",
            "description": "List online players.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_player_position",
            "description": "Get entity position array for a player name.",
            "parameters": {
                "type": "object",
                "properties": {"player": {"type": "string"}},
                "required": ["player"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backup_now",
            "description": "Trigger an immediate world backup before destructive edits.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_box",
            "description": "Fill a cuboid (max ~200k blocks). Use for platforms and walls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "z1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                    "z2": {"type": "integer"},
                    "block": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["replace", "hollow", "outline", "destroy", "keep"],
                    },
                },
                "required": ["x1", "y1", "z1", "x2", "y2", "z2", "block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_platform",
            "description": "Centered flat platform at y.",
            "parameters": {
                "type": "object",
                "properties": {
                    "center_x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "center_z": {"type": "integer"},
                    "width": {"type": "integer"},
                    "depth": {"type": "integer"},
                    "block": {"type": "string"},
                },
                "required": ["center_x", "y", "center_z", "width", "depth", "block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_sphere",
            "description": "Sphere or hollow sphere (radius 1-24).",
            "parameters": {
                "type": "object",
                "properties": {
                    "center_x": {"type": "integer"},
                    "center_y": {"type": "integer"},
                    "center_z": {"type": "integer"},
                    "radius": {"type": "integer"},
                    "block": {"type": "string"},
                    "hollow": {"type": "boolean"},
                },
                "required": ["center_x", "center_y", "center_z", "radius", "block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_cylinder",
            "description": "Vertical cylinder tower or shaft.",
            "parameters": {
                "type": "object",
                "properties": {
                    "center_x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "center_z": {"type": "integer"},
                    "radius": {"type": "integer"},
                    "height": {"type": "integer"},
                    "block": {"type": "string"},
                    "hollow": {"type": "boolean"},
                },
                "required": ["center_x", "y", "center_z", "radius", "height", "block"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_spiral_staircase",
            "description": "Spiral stairs with center pillar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "center_x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "center_z": {"type": "integer"},
                    "height": {"type": "integer"},
                    "radius": {"type": "integer"},
                    "block": {"type": "string"},
                },
                "required": ["center_x", "y", "center_z", "height", "radius"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fawe_as_player",
            "description": "Run a WorldEdit/FAWE command as the player at their location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "command": {"type": "string", "description": "e.g. //sphere glass 10"},
                },
                "required": ["player", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fawe_sphere_at_player",
            "description": "FAWE sphere centered on player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "block": {"type": "string"},
                    "radius": {"type": "integer"},
                },
                "required": ["player", "block", "radius"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mine_shaft_at_player",
            "description": "Dig a vertical air cylinder below player (fast mining assist).",
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "depth": {"type": "integer"},
                },
                "required": ["player"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "give_haste",
            "description": "Grant haste for faster mining.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "duration_sec": {"type": "integer"},
                    "amplifier": {"type": "integer"},
                },
                "required": ["player"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "teleport_player",
            "description": "Teleport player to coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"},
                },
                "required": ["player", "x", "y", "z"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "say",
            "description": "Broadcast a server message.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_time",
            "description": "Set world time (day, night, noon, etc.).",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_weather",
            "description": "Set weather clear, rain, or thunder.",
            "parameters": {
                "type": "object",
                "properties": {"weather": {"type": "string"}},
                "required": ["weather"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Raw RCON escape hatch. Avoid for large builds; prefer typed tools.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]
