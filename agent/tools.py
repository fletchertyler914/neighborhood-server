"""Shared Minecraft tool implementations for MCP and in-game orchestrator."""

from __future__ import annotations

import json
import math
import os
import socket
import struct
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.safety import guard_rcon_command

CONTAINER = os.environ.get("MC_CONTAINER", "mc-lan")
RCON_MODE = os.environ.get("RCON_MODE", "exec").lower()
RCON_HOST = os.environ.get("RCON_HOST", "mc")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD", "")
RCON_PASSWORD_FILE = os.environ.get("RCON_PASSWORD_FILE", "")
MAX_BLOCKS = int(os.environ.get("MINECRAFT_MCP_MAX_BLOCKS", "200000"))
MAX_COMMANDS = int(os.environ.get("MINECRAFT_MCP_MAX_COMMANDS", "20000"))
REPO_ROOT = os.environ.get(
    "NEIGHBORHOOD_REPO", os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)


@dataclass(frozen=True)
class Vec3:
    x: int
    y: int
    z: int


@dataclass
class ToolResult:
    ok: bool
    tool: str
    output: str
    commands: list[str] = field(default_factory=list)
    block_estimate: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "output": self.output,
            "commands": self.commands,
            "block_estimate": self.block_estimate,
            "error": self.error,
        }

    def summary(self) -> str:
        if self.error:
            return f"[{self.tool}] ERROR: {self.error}"
        return f"[{self.tool}] {self.output}"


def _run(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    output = output.strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"command failed with exit {result.returncode}")
    return output


def _rcon(command: str, timeout: int = 30) -> str:
    guard_rcon_command(command)
    if RCON_MODE == "tcp":
        return _rcon_tcp(command, timeout=timeout)
    return _run(
        ["docker", "exec", "-i", CONTAINER, "rcon-cli", command],
        timeout=timeout,
    )


def _rcon_password() -> str:
    if RCON_PASSWORD:
        return RCON_PASSWORD
    if RCON_PASSWORD_FILE:
        with open(RCON_PASSWORD_FILE, encoding="utf-8") as f:
            return f.read().strip()
    raise RuntimeError("RCON_PASSWORD or RCON_PASSWORD_FILE is required for RCON_MODE=tcp")


def _rcon_packet(request_id: int, packet_type: int, body: str) -> bytes:
    payload = body.encode("utf-8") + b"\x00\x00"
    size = 4 + 4 + len(payload)
    return struct.pack("<iii", size, request_id, packet_type) + payload


def _read_rcon_packet(sock: socket.socket) -> tuple[int, int, str]:
    raw_size = sock.recv(4)
    if len(raw_size) != 4:
        raise RuntimeError("short RCON response")
    (size,) = struct.unpack("<i", raw_size)
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    if len(data) != size:
        raise RuntimeError("incomplete RCON response")
    request_id, packet_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, body


def _rcon_tcp(command: str, timeout: int = 30) -> str:
    password = _rcon_password()
    with socket.create_connection((RCON_HOST, RCON_PORT), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(_rcon_packet(1, 3, password))
        auth_id, _, auth_body = _read_rcon_packet(sock)
        if auth_id == -1:
            raise RuntimeError("RCON authentication failed")
        # Some servers send an empty auth response before the real one.
        if auth_id != 1:
            auth_id, _, auth_body = _read_rcon_packet(sock)
            if auth_id == -1:
                raise RuntimeError("RCON authentication failed")
        sock.sendall(_rcon_packet(2, 2, command))
        _, _, body = _read_rcon_packet(sock)
        return body.strip()


def _quote_player(player: str) -> str:
    if " " in player:
        return f'"{player}"'
    return player


_MC_ERROR_PREFIXES = (
    "incorrect argument",
    "unknown or incomplete command",
    "expected ",
    "no targets matched",
    "unknown command",
    "you do not have permission",
    "unparseable",
    "invalid command",
    "no entity was found",
    "that position is not loaded",
)


def _looks_like_mc_error(out: str) -> bool:
    head = (out or "").lstrip().lower()
    return any(head.startswith(p) for p in _MC_ERROR_PREFIXES)


def _first_line(out: str) -> str:
    for line in (out or "").splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _volume(a: Vec3, b: Vec3) -> int:
    return (abs(a.x - b.x) + 1) * (abs(a.y - b.y) + 1) * (abs(a.z - b.z) + 1)


def _guard_volume(a: Vec3, b: Vec3, max_blocks: int = MAX_BLOCKS) -> int:
    volume = _volume(a, b)
    if volume > max_blocks:
        raise ValueError(
            f"refusing to modify {volume:,} blocks; limit is {max_blocks:,}"
        )
    return volume


def _guard_commands(count: int) -> None:
    if count > MAX_COMMANDS:
        raise ValueError(
            f"refusing to run {count:,} commands; limit is {MAX_COMMANDS:,}"
        )


def _run_many(commands: list[str], timeout: int = 180) -> tuple[str, list[str]]:
    _guard_commands(len(commands))
    outputs: list[str] = []
    for command in commands:
        out = _rcon(command, timeout=timeout)
        if _looks_like_mc_error(out):
            raise RuntimeError(f"{_first_line(out)} while running: {command}")
        outputs.append(out)
    text = f"ran {len(commands)} commands\n" + "\n".join(o for o in outputs if o)
    return text, commands


def _ok(tool: str, output: str, commands: list[str] | None = None, blocks: int = 0) -> ToolResult:
    return ToolResult(ok=True, tool=tool, output=output, commands=commands or [], block_estimate=blocks)


def _err(tool: str, exc: Exception) -> ToolResult:
    return ToolResult(ok=False, tool=tool, output="", error=str(exc))


# --- Tool implementations ---


def server_status() -> ToolResult:
    try:
        if RCON_MODE == "tcp":
            players = _rcon("list")
            return _ok("server_status", f"RCON mode: tcp ({RCON_HOST}:{RCON_PORT})\n{players}")
        ps = _run(["docker", "compose", "-f", os.path.join(REPO_ROOT, "docker-compose.yml"), "ps"], timeout=15)
        players = _rcon("list")
        return _ok("server_status", f"{ps}\n\n{players}")
    except Exception as e:
        return _err("server_status", e)


def preflight() -> ToolResult:
    try:
        if RCON_MODE == "tcp":
            players = _rcon("list")
            return _ok("preflight", f"rcon_ready=true\n{players}")
        status = _run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
            timeout=10,
        )
        players = _rcon("list")
        return _ok("preflight", f"container_health={status}\n{players}")
    except Exception as e:
        return _err("preflight", e)


def backup_now() -> ToolResult:
    try:
        if RCON_MODE == "tcp":
            out = _rcon("save-all flush", timeout=120)
            return _ok(
                "backup_now",
                "world flushed to disk; scheduled mc-backup archives it on the next interval\n"
                + out,
                commands=["save-all flush"],
            )
        out = _run(
            ["docker", "exec", "-i", "mc-backup", "backup", "now"],
            timeout=120,
        )
        return _ok("backup_now", out or "backup triggered")
    except Exception:
        try:
            out = _run(["docker", "exec", "-i", "mc-backup", "/opt/backup-loop.sh", "now"], timeout=120)
            return _ok("backup_now", out or "backup triggered")
        except Exception as e:
            return _err("backup_now", e)


def list_players() -> ToolResult:
    try:
        return _ok("list_players", _rcon("list"))
    except Exception as e:
        return _err("list_players", e)


def get_player_position(player: str) -> ToolResult:
    try:
        out = _rcon(f"data get entity {_quote_player(player)} Pos")
        return _ok("get_player_position", out)
    except Exception as e:
        return _err("get_player_position", e)


def get_player_dimension(player: str) -> ToolResult:
    try:
        out = _rcon(f"data get entity {_quote_player(player)} Dimension")
        return _ok("get_player_dimension", out)
    except Exception as e:
        return _err("get_player_dimension", e)


def run_command(command: str) -> ToolResult:
    try:
        command = command.lstrip("/")
        out = _rcon(command)
        if _looks_like_mc_error(out):
            return ToolResult(
                ok=False,
                tool="run_command",
                output=out,
                commands=[command],
                error=_first_line(out),
            )
        return _ok("run_command", out, commands=[command])
    except Exception as e:
        return _err("run_command", e)


def op_player(player: str) -> ToolResult:
    try:
        cmd = f"op {_quote_player(player)}"
        return _ok("op_player", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("op_player", e)


def teleport_player(player: str, x: int, y: int, z: int) -> ToolResult:
    try:
        cmd = f"tp {_quote_player(player)} {x} {y} {z}"
        return _ok("teleport_player", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("teleport_player", e)


def say(message: str) -> ToolResult:
    try:
        cmd = f"say {message}"
        return _ok("say", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("say", e)


def set_gamemode(player: str, mode: str) -> ToolResult:
    try:
        cmd = f"gamemode {mode} {_quote_player(player)}"
        return _ok("set_gamemode", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_gamemode", e)


def set_time(value: str) -> ToolResult:
    try:
        cmd = f"time set {value}"
        return _ok("set_time", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_time", e)


def set_weather(weather: str) -> ToolResult:
    try:
        cmd = f"weather {weather}"
        return _ok("set_weather", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_weather", e)


def give_haste(player: str, duration_sec: int = 600, amplifier: int = 2) -> ToolResult:
    """Speed mining with haste effect (creative-friendly boost)."""
    try:
        ticks = duration_sec * 20
        cmd = f"effect give {_quote_player(player)} haste {ticks} {amplifier}"
        return _ok("give_haste", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("give_haste", e)


def fill_box(
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    block: str,
    mode: Literal["replace", "hollow", "outline", "destroy", "keep"] = "replace",
) -> ToolResult:
    try:
        a, b = Vec3(x1, y1, z1), Vec3(x2, y2, z2)
        volume = _guard_volume(a, b)
        cmd = f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block} {mode}"
        out = _rcon(cmd, timeout=120)
        if _looks_like_mc_error(out):
            return ToolResult(
                ok=False,
                tool="fill_box",
                output=out,
                commands=[cmd],
                block_estimate=volume,
                error=_first_line(out),
            )
        return _ok(
            "fill_box",
            f"filled up to {volume:,} blocks using {block} ({mode})\n{out}",
            commands=[cmd],
            blocks=volume,
        )
    except Exception as e:
        return _err("fill_box", e)


def clear_box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> ToolResult:
    return fill_box(x1, y1, z1, x2, y2, z2, "air", "replace")


def build_platform(
    center_x: int, y: int, center_z: int, width: int, depth: int, block: str
) -> ToolResult:
    if width < 1 or depth < 1:
        return _err("build_platform", ValueError("width and depth must be positive"))
    x1 = center_x - width // 2
    x2 = x1 + width - 1
    z1 = center_z - depth // 2
    z2 = z1 + depth - 1
    return fill_box(x1, y, z1, x2, y, z2, block, "replace")


def build_sphere(
    center_x: int,
    center_y: int,
    center_z: int,
    radius: int,
    block: str,
    hollow: bool = True,
) -> ToolResult:
    try:
        if radius < 1 or radius > 24:
            raise ValueError("radius must be between 1 and 24")
        commands: list[str] = []
        r2 = radius * radius
        inner2 = max(radius - 1, 0) ** 2
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 > r2 or (hollow and d2 < inner2):
                        continue
                    commands.append(
                        f"setblock {center_x + dx} {center_y + dy} {center_z + dz} {block}"
                    )
        out, cmds = _run_many(commands)
        return _ok("build_sphere", out, commands=cmds, blocks=len(commands))
    except Exception as e:
        return _err("build_sphere", e)


def build_cylinder(
    center_x: int,
    y: int,
    center_z: int,
    radius: int,
    height: int,
    block: str,
    hollow: bool = False,
) -> ToolResult:
    try:
        if radius < 1 or radius > 32:
            raise ValueError("radius must be between 1 and 32")
        if height < 1 or height > 128:
            raise ValueError("height must be between 1 and 128")
        commands: list[str] = []
        r2 = radius * radius
        inner2 = max(radius - 1, 0) ** 2
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                d2 = dx * dx + dz * dz
                if d2 > r2 or (hollow and d2 < inner2):
                    continue
                commands.append(
                    f"fill {center_x + dx} {y} {center_z + dz} "
                    f"{center_x + dx} {y + height - 1} {center_z + dz} {block}"
                )
        out, cmds = _run_many(commands)
        return _ok("build_cylinder", out, commands=cmds, blocks=len(commands))
    except Exception as e:
        return _err("build_cylinder", e)


def build_spiral_staircase(
    center_x: int,
    y: int,
    center_z: int,
    height: int,
    radius: int,
    block: str = "smooth_stone",
    rail_block: str = "iron_bars",
) -> ToolResult:
    try:
        if height < 2 or height > 128:
            raise ValueError("height must be between 2 and 128")
        if radius < 2 or radius > 12:
            raise ValueError("radius must be between 2 and 12")
        commands = [
            f"fill {center_x} {y} {center_z} {center_x} {y + height} {center_z} {block}"
        ]
        for step in range(height):
            angle = step * (math.pi / 2)
            sx = center_x + round(math.cos(angle) * radius)
            sz = center_z + round(math.sin(angle) * radius)
            commands.append(f"setblock {sx} {y + step} {sz} {block}")
            commands.append(f"setblock {sx} {y + step + 1} {sz} air")
            rx = center_x + round(math.cos(angle) * (radius + 1))
            rz = center_z + round(math.sin(angle) * (radius + 1))
            commands.append(f"setblock {rx} {y + step} {rz} {rail_block}")
        out, cmds = _run_many(commands)
        return _ok("build_spiral_staircase", out, commands=cmds, blocks=len(commands))
    except Exception as e:
        return _err("build_spiral_staircase", e)


def fawe_as_player(player: str, command: str) -> ToolResult:
    try:
        command = command.strip()
        if not command:
            raise ValueError("command cannot be empty")
        # FAWE NPEs when run via `execute as <player> at @s run /sphere ...`
        # because `execute as` does not change the CommandSender — FAWE sees a
        # non-player Actor with no LocalSession/world/extent. The plugin's
        # console-only /agentexec dispatches via Player.performCommand, so FAWE
        # gets a real Player sender and the edit succeeds.
        verb = command.lstrip("/")
        cmd = f"agentexec {_quote_player(player)} //{verb}"
        out = _rcon(cmd, timeout=30)
        head = (out or "").lstrip()
        if _looks_like_mc_error(out) or head.startswith("ERROR"):
            return ToolResult(
                ok=False,
                tool="fawe_as_player",
                output=out,
                commands=[cmd],
                error=_first_line(out) or "agentexec failed",
            )
        if not head.startswith("OK"):
            return ToolResult(
                ok=False,
                tool="fawe_as_player",
                output=out,
                commands=[cmd],
                error="agentexec returned no acknowledgement (plugin not loaded?)",
            )
        return _ok("fawe_as_player", f"dispatched //{verb} as {player}", commands=[cmd])
    except Exception as e:
        return _err("fawe_as_player", e)


def _rename_tool(result: ToolResult, name: str) -> ToolResult:
    result.tool = name
    return result


def fawe_sphere_at_player(player: str, block: str, radius: int) -> ToolResult:
    return _rename_tool(fawe_as_player(player, f"//sphere {block} {radius}"), "fawe_sphere_at_player")


def fawe_cyl_at_player(player: str, block: str, radius: int, height: int) -> ToolResult:
    return _rename_tool(
        fawe_as_player(player, f"//cyl {block} {radius} {height}"), "fawe_cyl_at_player"
    )


def mine_shaft_at_player(player: str, depth: int = 32) -> ToolResult:
    """Dig a vertical shaft below the player using FAWE (fast mining assist)."""
    depth = max(1, min(depth, 64))
    return _rename_tool(fawe_as_player(player, f"//cyl air {2} {depth}"), "mine_shaft_at_player")


def execute_tool(name: str, arguments: dict[str, Any], dry_run: bool = False) -> ToolResult:
    """Dispatch a tool by name. Used by orchestrator and tests."""
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return _err(name, ValueError(f"unknown tool: {name}"))
    if dry_run:
        return ToolResult(
            ok=True,
            tool=name,
            output=f"dry-run: would call {name} with {json.dumps(arguments)}",
            commands=[],
        )
    return fn(**arguments)


TOOL_DISPATCH: dict[str, Any] = {
    "server_status": lambda **_: server_status(),
    "preflight": lambda **_: preflight(),
    "backup_now": lambda **_: backup_now(),
    "list_players": lambda **_: list_players(),
    "get_player_position": lambda player, **_: get_player_position(player),
    "get_player_dimension": lambda player, **_: get_player_dimension(player),
    "run_command": lambda command, **_: run_command(command),
    "op_player": lambda player, **_: op_player(player),
    "teleport_player": lambda player, x, y, z, **_: teleport_player(player, x, y, z),
    "say": lambda message, **_: say(message),
    "set_gamemode": lambda player, mode, **_: set_gamemode(player, mode),
    "set_time": lambda value, **_: set_time(value),
    "set_weather": lambda weather, **_: set_weather(weather),
    "give_haste": lambda player, duration_sec=600, amplifier=2, **_: give_haste(
        player, duration_sec, amplifier
    ),
    "fill_box": lambda x1, y1, z1, x2, y2, z2, block, mode="replace", **_: fill_box(
        x1, y1, z1, x2, y2, z2, block, mode
    ),
    "clear_box": lambda x1, y1, z1, x2, y2, z2, **_: clear_box(x1, y1, z1, x2, y2, z2),
    "build_platform": lambda center_x, y, center_z, width, depth, block, **_: build_platform(
        center_x, y, center_z, width, depth, block
    ),
    "build_sphere": lambda center_x, center_y, center_z, radius, block, hollow=True, **_: build_sphere(
        center_x, center_y, center_z, radius, block, hollow
    ),
    "build_cylinder": lambda center_x, y, center_z, radius, height, block, hollow=False, **_: build_cylinder(
        center_x, y, center_z, radius, height, block, hollow
    ),
    "build_spiral_staircase": lambda center_x, y, center_z, height, radius, block="smooth_stone", rail_block="iron_bars", **_: build_spiral_staircase(
        center_x, y, center_z, height, radius, block, rail_block
    ),
    "fawe_as_player": lambda player, command, **_: fawe_as_player(player, command),
    "fawe_sphere_at_player": lambda player, block, radius, **_: fawe_sphere_at_player(
        player, block, radius
    ),
    "fawe_cyl_at_player": lambda player, block, radius, height, **_: fawe_cyl_at_player(
        player, block, radius, height
    ),
    "mine_shaft_at_player": lambda player, depth=32, **_: mine_shaft_at_player(player, depth),
}
