"""Minecraft MCP Core v1 — stable public contract surface.

Capability tiers, tool family groupings, and compatibility metadata used by
MCP clients, orchestrator, and conformance tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

MCP_CORE_VERSION = "1.0.0"
TOOLS_VERSION_EXPECTED = "2.6.0"

# --- Capability tiers -------------------------------------------------------

CORE_REQUIRED: FrozenSet[str] = frozenset(
    {
        "server_status",
        "preflight",
        "list_players",
        "get_player_position",
        "get_player_dimension",
        "backup_now",
        "set_time",
        "set_weather",
        "set_gamemode",
        "teleport_player",
        "say",
        "fill_box",
        "clear_box",
        "build_platform",
        "build_sphere",
        "build_cylinder",
        "build_spiral_staircase",
    }
)

CORE_PLUS_BUILDERS: FrozenSet[str] = frozenset(
    {
        "build_house",
        "build_house_at_player",
        "build_castle_at_player",
        "build_animal_pen_at_player",
        "build_bridge_at_player",
        "build_wall_at_player",
        "mine_shaft_at_player",
        "give_item",
        "give_haste",
        "summon_entity",
        "op_player",
    }
)

CORE_PLUS_FAWE_SELECTION: FrozenSet[str] = frozenset(
    {
        "select_box",
        "select_around_player",
        "expand_selection",
        "contract_selection",
        "selection_size",
    }
)

CORE_PLUS_FAWE_TRANSFORM: FrozenSet[str] = frozenset(
    {
        "set_selection",
        "replace_in_selection",
        "walls_in_selection",
        "faces_in_selection",
        "hollow_selection",
        "overlay_selection",
    }
)

CORE_PLUS_FAWE_MOTION: FrozenSet[str] = frozenset(
    {
        "stack_selection",
        "move_selection",
        "rotate_selection",
        "flip_selection",
        "copy_selection",
        "cut_selection",
        "paste_selection_at_player",
    }
)

CORE_PLUS_FAWE_SHAPING: FrozenSet[str] = frozenset(
    {
        "generate_pyramid_at_player",
        "generate_forest_at_player",
        "smooth_selection",
        "naturalize_selection",
        "undo",
        "redo",
        "fawe_sphere_at_player",
        "fawe_cyl_at_player",
    }
)

CORE_PLUS_TEMPLATES: FrozenSet[str] = frozenset(
    {
        "list_templates",
        "paste_template_at_player",
        "create_template_from_selection",
    }
)

CORE_ESCAPE: FrozenSet[str] = frozenset(
    {
        "fawe_as_player",
        "run_command",
    }
)

CORE_PLUS: FrozenSet[str] = (
    CORE_PLUS_BUILDERS
    | CORE_PLUS_FAWE_SELECTION
    | CORE_PLUS_FAWE_TRANSFORM
    | CORE_PLUS_FAWE_MOTION
    | CORE_PLUS_FAWE_SHAPING
    | CORE_PLUS_TEMPLATES
)

ALL_CORE_V1: FrozenSet[str] = CORE_REQUIRED | CORE_PLUS | CORE_ESCAPE

FAWE_DIRECTIONS = frozenset(
    {
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
    }
)

ROTATION_YAWS = frozenset({0, 90, 180, 270})


@dataclass(frozen=True)
class ServerCapabilities:
    """Advertised MCP capabilities for a running server."""

    mcp_core_version: str = MCP_CORE_VERSION
    tools_version: str = TOOLS_VERSION_EXPECTED
    core_required: bool = True
    core_plus: bool = True
    template_ecosystem: bool = True
    deterministic_executor: bool = True
    community_ingest: bool = True
    community_publish: bool = True

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "mcp_core_version": self.mcp_core_version,
            "tools_version": self.tools_version,
            "core_required": self.core_required,
            "core_plus": self.core_plus,
            "template_ecosystem": self.template_ecosystem,
            "deterministic_executor": self.deterministic_executor,
            "community_ingest": self.community_ingest,
            "community_publish": self.community_publish,
        }


def default_capabilities(*, tools_version: str) -> ServerCapabilities:
    return ServerCapabilities(tools_version=tools_version)


def missing_tools(available: set[str], required: FrozenSet[str]) -> list[str]:
    return sorted(required - available)
