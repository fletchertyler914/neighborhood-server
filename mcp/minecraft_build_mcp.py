#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.16.0",
# ]
# ///
"""Thin Cursor MCP adapter over agent.tools."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

# Repo root on sys.path so `agent` imports work when run via uv --script
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mcp.server.fastmcp import FastMCP

from agent import tools as T

mcp = FastMCP("neighborhood-minecraft-builder")


def _text(result: T.ToolResult) -> str:
    return result.summary() if not result.ok else result.output or result.summary()


@mcp.tool()
def server_status() -> str:
    """Show Docker service status and the current Minecraft player list."""
    return _text(T.server_status())


@mcp.tool()
def preflight() -> str:
    """Check container health and online players."""
    return _text(T.preflight())


@mcp.tool()
def backup_now() -> str:
    """Trigger an immediate world backup."""
    return _text(T.backup_now())


@mcp.tool()
def run_command(command: str) -> str:
    """Run a raw Minecraft/RCON command. Do not include a leading slash."""
    return _text(T.run_command(command))


@mcp.tool()
def list_players() -> str:
    """List online players."""
    return _text(T.list_players())


@mcp.tool()
def get_player_position(player: str) -> str:
    """Get a player's position (NBT Pos array)."""
    return _text(T.get_player_position(player))


@mcp.tool()
def get_player_dimension(player: str) -> str:
    """Get a player's dimension."""
    return _text(T.get_player_dimension(player))


@mcp.tool()
def op_player(player: str) -> str:
    """Make a player an operator. Bedrock names usually start with a dot."""
    return _text(T.op_player(player))


@mcp.tool()
def teleport_player(player: str, x: int, y: int, z: int) -> str:
    """Teleport a player to exact coordinates."""
    return _text(T.teleport_player(player, x, y, z))


@mcp.tool()
def say(message: str) -> str:
    """Broadcast a server chat message."""
    return _text(T.say(message))


@mcp.tool()
def set_gamemode(player: str, mode: str) -> str:
    """Set gamemode for a player (creative, survival, adventure, spectator)."""
    return _text(T.set_gamemode(player, mode))


@mcp.tool()
def set_time(value: str) -> str:
    """Set world time (e.g. day, night, noon)."""
    return _text(T.set_time(value))


@mcp.tool()
def set_weather(weather: str) -> str:
    """Set weather: clear, rain, or thunder."""
    return _text(T.set_weather(weather))


@mcp.tool()
def give_haste(player: str, duration_sec: int = 600, amplifier: int = 2) -> str:
    """Grant haste for faster mining."""
    return _text(T.give_haste(player, duration_sec, amplifier))


@mcp.tool()
def fill_box(
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    block: str,
    mode: Literal["replace", "hollow", "outline", "destroy", "keep"] = "replace",
) -> str:
    """Fill a rectangular cuboid with a block, guarded by max block count."""
    return _text(T.fill_box(x1, y1, z1, x2, y2, z2, block, mode))


@mcp.tool()
def clear_box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> str:
    """Clear a cuboid to air, guarded by max block count."""
    return _text(T.clear_box(x1, y1, z1, x2, y2, z2))


@mcp.tool()
def build_platform(
    center_x: int, y: int, center_z: int, width: int, depth: int, block: str
) -> str:
    """Build a centered rectangular platform."""
    return _text(T.build_platform(center_x, y, center_z, width, depth, block))


@mcp.tool()
def build_sphere(
    center_x: int,
    center_y: int,
    center_z: int,
    radius: int,
    block: str,
    hollow: bool = True,
) -> str:
    """Build a sphere or hollow sphere. Max radius: 24."""
    return _text(T.build_sphere(center_x, center_y, center_z, radius, block, hollow))


@mcp.tool()
def build_cylinder(
    center_x: int,
    y: int,
    center_z: int,
    radius: int,
    height: int,
    block: str,
    hollow: bool = False,
) -> str:
    """Build a vertical cylinder. Max radius: 32, max height: 128."""
    return _text(T.build_cylinder(center_x, y, center_z, radius, height, block, hollow))


@mcp.tool()
def build_spiral_staircase(
    center_x: int,
    y: int,
    center_z: int,
    height: int,
    radius: int,
    block: str = "smooth_stone",
    rail_block: str = "iron_bars",
) -> str:
    """Build a simple spiral staircase with a center pillar and outer rail."""
    return _text(
        T.build_spiral_staircase(center_x, y, center_z, height, radius, block, rail_block)
    )


@mcp.tool()
def fawe_as_player(player: str, command: str) -> str:
    """Run a FastAsyncWorldEdit command as an online player at their location."""
    return _text(T.fawe_as_player(player, command))


@mcp.tool()
def fawe_sphere_at_player(player: str, block: str, radius: int) -> str:
    """FAWE sphere centered on player."""
    return _text(T.fawe_sphere_at_player(player, block, radius))


@mcp.tool()
def mine_shaft_at_player(player: str, depth: int = 32) -> str:
    """Dig a vertical air shaft below the player (fast mining assist)."""
    return _text(T.mine_shaft_at_player(player, depth))


if __name__ == "__main__":
    mcp.run()
