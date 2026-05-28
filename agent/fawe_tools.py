"""Typed FAWE primitive tools — deterministic command bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.mcp_core import FAWE_DIRECTIONS, ROTATION_YAWS

if TYPE_CHECKING:
    from agent.tools import ToolResult


def _tools():
    from agent import tools as t

    return t


def _fawe(player: str, verb: str) -> "ToolResult":
    return _tools().fawe_as_player(player, f"//{verb}")


def _dir(direction: str) -> str:
    d = (direction or "me").strip().lower()
    if d not in FAWE_DIRECTIONS:
        raise ValueError(f"invalid direction {direction!r}")
    return d


def select_box(
    player: str,
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
) -> "ToolResult":
    try:
        cmds = [
            f"//pos1 {x1},{y1},{z1}",
            f"//pos2 {x2},{y2},{z2}",
        ]
        parts = []
        commands: list[str] = []
        for verb in cmds:
            r = _fawe(player, verb.lstrip("/"))
            if not r.ok:
                return r
            parts.append(r.output or "")
            commands.extend(r.commands)
        return _tools()._ok(
            "select_box",
            f"selection {x1},{y1},{z1} -> {x2},{y2},{z2}\n" + "\n".join(parts),
            commands=commands,
        )
    except Exception as e:
        return _tools()._err("select_box", e)


def select_around_player(
    player: str,
    width: int,
    depth: int,
    height: int,
    offset_y: int = 0,
) -> "ToolResult":
    try:
        facing = _tools()._player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")
        w, d, h = max(1, int(width)), max(1, int(depth)), max(1, int(height))
        oy = int(offset_y)
        half_w, half_d = w // 2, d // 2
        cx = facing.x + facing.forward_dx * (half_d + 1)
        cz = facing.z + facing.forward_dz * (half_d + 1)
        cy = facing.y + oy
        return select_box(
            player,
            cx - half_w,
            cy,
            cz - half_w,
            cx + half_w,
            cy + h - 1,
            cz + half_w,
        )
    except Exception as e:
        return _tools()._err("select_around_player", e)


def expand_selection(player: str, amount: int, direction: str = "up") -> "ToolResult":
    try:
        n = max(1, min(int(amount), 256))
        d = _dir(direction)
        return _tools()._rename_tool(
            _fawe(player, f"expand {n} {d}"), "expand_selection"
        )
    except Exception as e:
        return _tools()._err("expand_selection", e)


def contract_selection(player: str, amount: int, direction: str = "up") -> "ToolResult":
    try:
        n = max(1, min(int(amount), 256))
        d = _dir(direction)
        return _tools()._rename_tool(
            _fawe(player, f"contract {n} {d}"), "contract_selection"
        )
    except Exception as e:
        return _tools()._err("contract_selection", e)


def selection_size(player: str) -> "ToolResult":
    try:
        return _tools()._rename_tool(_fawe(player, "size"), "selection_size")
    except Exception as e:
        return _tools()._err("selection_size", e)


def set_selection(player: str, pattern: str) -> "ToolResult":
    try:
        if not (pattern or "").strip():
            raise ValueError("pattern is required")
        return _tools()._rename_tool(_fawe(player, f"set {pattern.strip()}"), "set_selection")
    except Exception as e:
        return _tools()._err("set_selection", e)


def replace_in_selection(player: str, from_blocks: str, to_pattern: str) -> "ToolResult":
    try:
        fb = (from_blocks or "").strip()
        tp = (to_pattern or "").strip()
        if not fb or not tp:
            raise ValueError("from_blocks and to_pattern are required")
        return _tools()._rename_tool(
            _fawe(player, f"replace {fb} {tp}"), "replace_in_selection"
        )
    except Exception as e:
        return _tools()._err("replace_in_selection", e)


def walls_in_selection(player: str, pattern: str) -> "ToolResult":
    try:
        p = (pattern or "").strip()
        if not p:
            raise ValueError("pattern is required")
        return _tools()._rename_tool(_fawe(player, f"walls {p}"), "walls_in_selection")
    except Exception as e:
        return _tools()._err("walls_in_selection", e)


def faces_in_selection(player: str, pattern: str) -> "ToolResult":
    try:
        p = (pattern or "").strip()
        if not p:
            raise ValueError("pattern is required")
        return _tools()._rename_tool(_fawe(player, f"faces {p}"), "faces_in_selection")
    except Exception as e:
        return _tools()._err("faces_in_selection", e)


def hollow_selection(player: str, thickness: int = 1, pattern: str = "air") -> "ToolResult":
    try:
        t = max(1, min(int(thickness), 16))
        p = (pattern or "air").strip()
        return _tools()._rename_tool(
            _fawe(player, f"hollow {t} {p}"), "hollow_selection"
        )
    except Exception as e:
        return _tools()._err("hollow_selection", e)


def overlay_selection(player: str, pattern: str) -> "ToolResult":
    try:
        p = (pattern or "").strip()
        if not p:
            raise ValueError("pattern is required")
        return _tools()._rename_tool(_fawe(player, f"overlay {p}"), "overlay_selection")
    except Exception as e:
        return _tools()._err("overlay_selection", e)


def stack_selection(player: str, count: int, direction: str = "me") -> "ToolResult":
    try:
        n = max(1, min(int(count), 64))
        d = _dir(direction)
        return _tools()._rename_tool(
            _fawe(player, f"stack {n} {d}"), "stack_selection"
        )
    except Exception as e:
        return _tools()._err("stack_selection", e)


def move_selection(player: str, amount: int, direction: str = "me") -> "ToolResult":
    try:
        n = max(1, min(int(amount), 256))
        d = _dir(direction)
        return _tools()._rename_tool(
            _fawe(player, f"move {n} {d}"), "move_selection"
        )
    except Exception as e:
        return _tools()._err("move_selection", e)


def rotate_selection(player: str, yaw: int) -> "ToolResult":
    try:
        y = int(yaw) % 360
        if y not in ROTATION_YAWS:
            raise ValueError("yaw must be 0, 90, 180, or 270")
        return _tools()._rename_tool(_fawe(player, f"rotate {y}"), "rotate_selection")
    except Exception as e:
        return _tools()._err("rotate_selection", e)


def flip_selection(player: str, direction: str = "me") -> "ToolResult":
    try:
        d = _dir(direction)
        return _tools()._rename_tool(_fawe(player, f"flip {d}"), "flip_selection")
    except Exception as e:
        return _tools()._err("flip_selection", e)


def copy_selection(player: str) -> "ToolResult":
    try:
        return _tools()._rename_tool(_fawe(player, "copy"), "copy_selection")
    except Exception as e:
        return _tools()._err("copy_selection", e)


def cut_selection(player: str) -> "ToolResult":
    try:
        return _tools()._rename_tool(_fawe(player, "cut"), "cut_selection")
    except Exception as e:
        return _tools()._err("cut_selection", e)


def paste_selection_at_player(player: str, ignore_air: bool = True) -> "ToolResult":
    try:
        flags = "-a" if ignore_air else ""
        verb = f"paste {flags}".strip()
        return _tools()._rename_tool(_fawe(player, verb), "paste_selection_at_player")
    except Exception as e:
        return _tools()._err("paste_selection_at_player", e)


def generate_pyramid_at_player(
    player: str,
    pattern: str,
    size: int,
    hollow: bool = False,
) -> "ToolResult":
    try:
        s = max(1, min(int(size), 64))
        p = (pattern or "").strip()
        if not p:
            raise ValueError("pattern is required")
        cmd = "hpyramid" if hollow else "pyramid"
        return _tools()._rename_tool(
            _fawe(player, f"{cmd} {p} {s}"), "generate_pyramid_at_player"
        )
    except Exception as e:
        return _tools()._err("generate_pyramid_at_player", e)


def generate_forest_at_player(
    player: str,
    size: int,
    tree_type: str = "tree",
    density: float = 0.5,
) -> "ToolResult":
    try:
        s = max(1, min(int(size), 64))
        tt = (tree_type or "tree").strip()
        den = max(0.0, min(float(density), 1.0))
        return _tools()._rename_tool(
            _fawe(player, f"forestgen {s} {tt} {den}"), "generate_forest_at_player"
        )
    except Exception as e:
        return _tools()._err("generate_forest_at_player", e)


def smooth_selection(player: str, iterations: int = 1) -> "ToolResult":
    try:
        it = max(1, min(int(iterations), 10))
        return _tools()._rename_tool(
            _fawe(player, f"smooth {it}"), "smooth_selection"
        )
    except Exception as e:
        return _tools()._err("smooth_selection", e)


def naturalize_selection(player: str) -> "ToolResult":
    try:
        return _tools()._rename_tool(_fawe(player, "naturalize"), "naturalize_selection")
    except Exception as e:
        return _tools()._err("naturalize_selection", e)


def undo(player: str, count: int = 1) -> "ToolResult":
    try:
        n = max(1, min(int(count), 32))
        verb = f"undo {n}" if n > 1 else "undo"
        return _tools()._rename_tool(_fawe(player, verb), "undo")
    except Exception as e:
        return _tools()._err("undo", e)


def redo(player: str, count: int = 1) -> "ToolResult":
    try:
        n = max(1, min(int(count), 32))
        verb = f"redo {n}" if n > 1 else "redo"
        return _tools()._rename_tool(_fawe(player, verb), "redo")
    except Exception as e:
        return _tools()._err("redo", e)
