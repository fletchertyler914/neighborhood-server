"""Live world-state context injection for the agent.

We pull a small, fast snapshot from the running server before the LLM call
so it doesn't have to guess things like the player's facing direction, the
ground level under their feet, or the current time. Failures here MUST NOT
fail the job — context is best-effort.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from agent import tools as T
from agent.safety import audit_log_path

_POS_RX = re.compile(r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]")
_ROT_RX = re.compile(r"\[([-\d.]+)f?,\s*([-\d.]+)f?\]")


@dataclass
class WorldContext:
    online_players: list[str]
    time_of_day: str
    facing: str
    ground_block: str | None
    ground_y: int | None
    last_actions: list[str]

    def render(self) -> str:
        parts = [
            f"- Online players: {', '.join(self.online_players) or 'none'}",
            f"- Time: {self.time_of_day}",
            f"- Player facing: {self.facing}",
        ]
        if self.ground_block:
            parts.append(
                f"- Ground under player: {self.ground_block} at y={self.ground_y}"
            )
        if self.last_actions:
            parts.append("- Recent agent actions:")
            for a in self.last_actions:
                parts.append(f"  - {a}")
        return "## Live world context\n\n" + "\n".join(parts)


def _safe_rcon(cmd: str) -> str:
    try:
        return T._rcon(cmd, timeout=5)
    except Exception:
        return ""


def _parse_player_list(out: str) -> list[str]:
    if ":" not in out:
        return []
    _, _, tail = out.partition(":")
    return [p.strip() for p in tail.split(",") if p.strip()]


def _parse_time(out: str) -> str:
    m = re.search(r"(\d+)", out or "")
    if not m:
        return "unknown"
    ticks = int(m.group(1)) % 24000
    if ticks < 6000:
        return "morning"
    if ticks < 12000:
        return "noon"
    if ticks < 13000:
        return "evening"
    if ticks < 18000:
        return "night"
    return "late night"


def _player_rotation(player: str) -> str:
    out = _safe_rcon(f"data get entity {T._quote_player(player)} Rotation")
    m = _ROT_RX.search(out or "")
    if not m:
        return "unknown"
    yaw = float(m.group(1)) % 360
    if 315 <= yaw or yaw < 45:
        return "south (+Z)"
    if 45 <= yaw < 135:
        return "west (-X)"
    if 135 <= yaw < 225:
        return "north (-Z)"
    return "east (+X)"


def _ground_under(player: str, x: float, y: float, z: float) -> tuple[str | None, int | None]:
    out = _safe_rcon(
        f"execute at {T._quote_player(player)} run data get block ~ ~-1 ~"
    )
    if not out:
        return None, None
    m = re.search(r"minecraft:([a-z0-9_]+)", out)
    block = m.group(1) if m else None
    return block, int(y) - 1


def _last_actions(player: str | None = None, limit: int = 3) -> list[str]:
    path: Path = audit_log_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-200:]
    except OSError:
        return []
    entries: list[str] = []
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if player and obj.get("player") != player:
            continue
        if obj.get("status") != "done":
            continue
        prompt = (obj.get("prompt") or "")[:80]
        tools = [tc.get("name") for tc in (obj.get("tool_calls") or [])][:3]
        if not prompt:
            continue
        entries.append(f'"{prompt}" -> {", ".join(tools) or "no tools"}')
        if len(entries) >= limit:
            break
    return entries


def gather(player: str, x: float, y: float, z: float) -> WorldContext:
    """Best-effort world-state snapshot. Never raises."""
    try:
        players = _parse_player_list(_safe_rcon("list"))
    except Exception:
        players = []
    try:
        time_of_day = _parse_time(_safe_rcon("time query daytime"))
    except Exception:
        time_of_day = "unknown"
    try:
        facing = _player_rotation(player)
    except Exception:
        facing = "unknown"
    try:
        block, ground_y = _ground_under(player, x, y, z)
    except Exception:
        block, ground_y = None, None
    try:
        recent = _last_actions(player)
    except Exception:
        recent = []
    return WorldContext(
        online_players=players,
        time_of_day=time_of_day,
        facing=facing,
        ground_block=block,
        ground_y=ground_y,
        last_actions=recent,
    )
