"""Shared Minecraft tool implementations for MCP and in-game orchestrator."""

from __future__ import annotations

import json
import math
import os
import re
import socket
import sys
import struct
import subprocess
from dataclasses import dataclass, field
from typing import Any, Literal

from agent.safety import guard_rcon_command
from agent.templates import catalog as template_catalog
from agent.tool_registry import build_dispatch, build_openai_schemas, validate_registry

CONTAINER = os.environ.get("MC_CONTAINER", "mc-lan")
RCON_MODE = os.environ.get("RCON_MODE", "exec").lower()
RCON_HOST = os.environ.get("RCON_HOST", "mc")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD = os.environ.get("RCON_PASSWORD", "")
RCON_PASSWORD_FILE = os.environ.get("RCON_PASSWORD_FILE", "")
MAX_BLOCKS = int(os.environ.get("MINECRAFT_MCP_MAX_BLOCKS", "200000"))
MAX_COMMANDS = int(os.environ.get("MINECRAFT_MCP_MAX_COMMANDS", "20000"))
REPO_ROOT = os.environ.get(
    "NEIGHBORHOOD_REPO",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
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
    deterministic_signature: str = ""
    execution_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "tool": self.tool,
            "output": self.output,
            "commands": self.commands,
            "block_estimate": self.block_estimate,
            "error": self.error,
        }
        if self.deterministic_signature:
            out["deterministic_signature"] = self.deterministic_signature
        if self.execution_metadata:
            out["execution_metadata"] = self.execution_metadata
        return out

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


_PLAYER_NAME_RX = re.compile(r"^\.?[A-Za-z0-9_]{1,16}$")
_BLOCK_ID_RX = re.compile(r"^[a-z0-9_]+$")


def validate_player_name(player: str) -> str:
    name = (player or "").strip()
    if not _PLAYER_NAME_RX.fullmatch(name):
        raise ValueError(f"invalid player name: {player!r}")
    return name


def _validate_block_id(block: str) -> str:
    name = (block or "").lower().removeprefix("minecraft:")
    if not _BLOCK_ID_RX.match(name):
        raise ValueError(f"invalid block id: {block!r}")
    return name


def _quote_player(player: str) -> str:
    name = validate_player_name(player)
    if " " in name:
        return f'"{name}"'
    return name


_MC_ERROR_PREFIXES = (
    "incorrect argument",
    "invalid integer",
    "unknown or incomplete command",
    "expected ",
    "no targets matched",
    "unknown command",
    "unknown item",
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
        text = " ".join((message or "").split())
        if not text:
            raise ValueError("message cannot be empty")
        cmd = f"say {text}"
        return _ok("say", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("say", e)


def set_gamemode(player: str, mode: str) -> ToolResult:
    try:
        norm = (mode or "").strip().lower()
        aliases = {"c": "creative", "s": "survival", "a": "adventure", "sp": "spectator"}
        norm = aliases.get(norm, norm)
        if norm not in {"survival", "creative", "adventure", "spectator"}:
            raise ValueError("mode must be survival|creative|adventure|spectator")
        cmd = f"gamemode {norm} {_quote_player(player)}"
        return _ok("set_gamemode", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_gamemode", e)


def set_time(value: str) -> ToolResult:
    try:
        norm = (value or "").strip().lower()
        aliases = {
            "morning": "day",
            "dawn": "day",
            "sunrise": "day",
            "afternoon": "noon",
            "dusk": "night",
            "sunset": "night",
            "evening": "night",
        }
        norm = aliases.get(norm, norm)
        allowed = {"day", "night", "noon", "midnight"}
        if norm not in allowed:
            raise ValueError("time must be day|night|noon|midnight (or alias)")
        cmd = f"time set {norm}"
        return _ok("set_time", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_time", e)


def set_weather(weather: str) -> ToolResult:
    try:
        norm = (weather or "").strip().lower()
        aliases = {"sun": "clear", "sunny": "clear", "storm": "thunder"}
        norm = aliases.get(norm, norm)
        if norm not in {"clear", "rain", "thunder"}:
            raise ValueError("weather must be clear|rain|thunder")
        cmd = f"weather {norm}"
        return _ok("set_weather", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("set_weather", e)


def give_haste(player: str, duration_sec: int = 600, amplifier: int = 2) -> ToolResult:
    """Speed mining with haste effect (creative-friendly boost)."""
    try:
        duration = max(1, min(int(duration_sec), 7200))
        amp = max(0, min(int(amplifier), 4))
        # Vanilla command expects seconds here, not ticks.
        cmd = f"effect give {_quote_player(player)} haste {duration} {amp}"
        return _ok("give_haste", _rcon(cmd), commands=[cmd])
    except Exception as e:
        return _err("give_haste", e)


# Aliases the LLM commonly produces when the user gives an under-specified
# item name. Map them to canonical Minecraft IDs. Diamond-tier defaults match
# how creative-mode players usually expect to be equipped.
_ITEM_ALIASES: dict[str, str] = {
    "pickaxe": "diamond_pickaxe",
    "pick": "diamond_pickaxe",
    "axe": "diamond_axe",
    "sword": "diamond_sword",
    "shovel": "diamond_shovel",
    "hoe": "diamond_hoe",
    "helmet": "diamond_helmet",
    "chestplate": "diamond_chestplate",
    "leggings": "diamond_leggings",
    "boots": "diamond_boots",
    "armor": "diamond_chestplate",
    "armour": "diamond_chestplate",
    "elytras": "elytra",
    "totem": "totem_of_undying",
    "ender pearl": "ender_pearl",
    "fire": "flint_and_steel",
    "torch": "torch",
    "torches": "torch",
}

_ITEM_DENYLIST: frozenset[str] = frozenset(
    {
        "command_block",
        "minecart_with_command_block",
        "chain_command_block",
        "repeating_command_block",
        "barrier",
        "structure_block",
        "structure_void",
        "jigsaw",
        "debug_stick",
        "spawner",
        "bedrock",
    }
)


def _normalize_item_id(item: str) -> str:
    """Best-effort normalization of LLM-supplied item names to Mojang IDs."""

    raw = (item or "").strip()
    raw = raw.removeprefix("minecraft:").lower()
    cleaned = raw.replace("-", "_").replace(" ", "_")
    if cleaned in _ITEM_ALIASES:
        return _ITEM_ALIASES[cleaned]
    # Drop trailing pluralization ("pickaxes" → "pickaxe").
    if cleaned.endswith("es") and cleaned[:-2] in _ITEM_ALIASES:
        return _ITEM_ALIASES[cleaned[:-2]]
    if cleaned.endswith("s") and cleaned[:-1] in _ITEM_ALIASES:
        return _ITEM_ALIASES[cleaned[:-1]]
    return cleaned


# Vanilla peaceful / neutral mobs the agent is allowed to summon without
# needing a destructive-style confirm token. Hostile and boss entities are
# omitted so a player can't /agent "summon 20 withers" by accident.
_ANIMAL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "allay",
        "armadillo",
        "axolotl",
        "bat",
        "bee",
        "camel",
        "cat",
        "chicken",
        "cod",
        "cow",
        "donkey",
        "fox",
        "frog",
        "glow_squid",
        "goat",
        "horse",
        "llama",
        "mooshroom",
        "mule",
        "ocelot",
        "panda",
        "parrot",
        "pig",
        "polar_bear",
        "pufferfish",
        "rabbit",
        "salmon",
        "sheep",
        "sniffer",
        "squid",
        "strider",
        "tadpole",
        "trader_llama",
        "tropical_fish",
        "turtle",
        "villager",
        "wandering_trader",
        "wolf",
    }
)

_ANIMAL_ALIASES: dict[str, str] = {
    "chickens": "chicken",
    "pigs": "pig",
    "cows": "cow",
    "sheeps": "sheep",
    "sheep": "sheep",
    "rabbits": "rabbit",
    "bunny": "rabbit",
    "bunnies": "rabbit",
    "horses": "horse",
    "goats": "goat",
    "llamas": "llama",
    "bees": "bee",
    "wolves": "wolf",
    "puppy": "wolf",
    "puppies": "wolf",
    "kitty": "cat",
    "kittens": "cat",
    "cats": "cat",
    "frogs": "frog",
    "turtles": "turtle",
    "foxes": "fox",
    "axolotls": "axolotl",
}

_ENTITY_DENYLIST: frozenset[str] = frozenset(
    {
        "wither",
        "ender_dragon",
        "warden",
        "elder_guardian",
    }
)


def _normalize_entity_id(entity: str) -> str:
    raw = (entity or "").strip().removeprefix("minecraft:").lower().replace(" ", "_")
    return _ANIMAL_ALIASES.get(raw, raw)


def summon_entity(
    entity: str,
    x: int,
    y: int,
    z: int,
    count: int = 1,
    nbt: str | None = None,
) -> ToolResult:
    """Summon vanilla entities at absolute coordinates.

    ``entity`` is a Mojang id (``chicken``, ``villager``, ``axolotl``).
    Aliases like ``chickens`` → ``chicken`` are normalized. Boss entities
    (``wither``, ``ender_dragon``, ``warden``, ``elder_guardian``) are
    refused. ``nbt`` is optional NBT to append to every summon, e.g.
    ``{NoAI:1b}``.
    """

    try:
        ent = _normalize_entity_id(entity)
        if not ent:
            raise ValueError("entity is required")
        if ent in _ENTITY_DENYLIST:
            raise PermissionError(f"entity not allowed: {ent}")
        n = max(1, min(int(count), 32))
        commands: list[str] = []
        tail = f" {nbt}" if nbt else ""
        for _ in range(n):
            commands.append(f"summon {ent} {x} {y} {z}{tail}")
        out, cmds = _run_many(commands)
        return _ok("summon_entity", out, commands=cmds, blocks=n)
    except Exception as e:
        return _err("summon_entity", e)


def give_item(
    player: str,
    item: str,
    count: int = 1,
    components: str | None = None,
) -> ToolResult:
    """Give a vanilla item to a player.

    ``item`` may be a Mojang id (``diamond_pickaxe``), an alias
    (``pickaxe`` → ``diamond_pickaxe``), or a fully namespaced id
    (``minecraft:diamond_pickaxe``). ``components`` is the optional
    1.20.5+ component block (``[minecraft:enchantments={...}]``) appended
    verbatim after the item id.
    """

    try:
        normalized = _normalize_item_id(item)
        if not normalized:
            raise ValueError("item is required")
        if normalized in _ITEM_DENYLIST:
            raise PermissionError(f"item not allowed: {normalized}")
        n = max(1, min(int(count), 64))
        spec = f"{normalized}{components}" if components else normalized
        cmd = f"give {_quote_player(player)} {spec} {n}"
        out = _rcon(cmd, timeout=15)
        if _looks_like_mc_error(out):
            return ToolResult(
                ok=False,
                tool="give_item",
                output=out,
                commands=[cmd],
                error=_first_line(out) or "give failed",
            )
        return _ok("give_item", out, commands=[cmd], blocks=n)
    except Exception as e:
        return _err("give_item", e)


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
        block = _validate_block_id(block)
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
    return _rename_tool(fill_box(x1, y1, z1, x2, y2, z2, "air", "replace"), "clear_box")


def count_blocks_in_box(
    block: str,
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
) -> ToolResult:
    try:
        from agent.world_auditor.snapshot import SnapshotBox, snapshot_box

        a, b = Vec3(x1, y1, z1), Vec3(x2, y2, z2)
        volume = _volume(a, b)
        if volume > int(os.environ.get("WORLD_AUDITOR_TOOL_MAX_BLOCKS", "50000")):
            raise ValueError(f"refusing to inspect {volume:,} blocks")
        block_id = block if ":" in block else f"minecraft:{block}"
        snap = snapshot_box(SnapshotBox(x1, y1, z1, x2, y2, z2), include_sparse=False)
        count = snap.palette.get(block_id, 0)
        payload = {
            "block": block_id,
            "count": count,
            "bbox": list(snap.box.as_tuple()),
            "source": snap.source,
        }
        return _ok("count_blocks_in_box", json.dumps(payload, sort_keys=True), blocks=volume)
    except Exception as e:
        return _err("count_blocks_in_box", e)


def palette_in_box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> ToolResult:
    try:
        from agent.world_auditor.snapshot import SnapshotBox, snapshot_box

        a, b = Vec3(x1, y1, z1), Vec3(x2, y2, z2)
        volume = _volume(a, b)
        if volume > int(os.environ.get("WORLD_AUDITOR_TOOL_MAX_BLOCKS", "50000")):
            raise ValueError(f"refusing to inspect {volume:,} blocks")
        snap = snapshot_box(SnapshotBox(x1, y1, z1, x2, y2, z2), include_sparse=False)
        payload = {
            "bbox": list(snap.box.as_tuple()),
            "palette": dict(sorted(snap.palette.items())),
            "source": snap.source,
        }
        return _ok("palette_in_box", json.dumps(payload, sort_keys=True), blocks=volume)
    except Exception as e:
        return _err("palette_in_box", e)


def verify_structure(
    check: str,
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    block: str | None = None,
    min_count: int | None = None,
    min_ratio: float | None = None,
    entity: str | None = None,
) -> ToolResult:
    try:
        from agent.world_auditor.invariants import verify_structure as run_check
        from agent.world_auditor.snapshot import SnapshotBox, snapshot_box

        a, b = Vec3(x1, y1, z1), Vec3(x2, y2, z2)
        volume = _volume(a, b)
        if volume > int(os.environ.get("WORLD_AUDITOR_TOOL_MAX_BLOCKS", "50000")):
            raise ValueError(f"refusing to inspect {volume:,} blocks")
        snap = snapshot_box(SnapshotBox(x1, y1, z1, x2, y2, z2), include_sparse=True)
        result = run_check(
            check,
            snap,
            block=block,
            min_count=min_count,
            min_ratio=min_ratio,
            entity=entity,
        )
        return _ok("verify_structure", json.dumps(result.to_dict(), sort_keys=True), blocks=volume)
    except Exception as e:
        return _err("verify_structure", e)


def build_platform(
    center_x: int, y: int, center_z: int, width: int, depth: int, block: str
) -> ToolResult:
    center_x, y, center_z = int(center_x), int(y), int(center_z)
    width, depth = int(width), int(depth)
    if width < 1 or depth < 1:
        return _err("build_platform", ValueError("width and depth must be positive"))
    x1 = center_x - width // 2
    x2 = x1 + width - 1
    z1 = center_z - depth // 2
    z2 = z1 + depth - 1
    return _rename_tool(
        fill_box(x1, y, z1, x2, y, z2, block, "replace"), "build_platform"
    )


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
        center_x, y, center_z = int(center_x), int(y), int(center_z)
        radius, height = int(radius), int(height)
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
        columns = len(commands)
        block_estimate = columns * height
        return _ok("build_cylinder", out, commands=cmds, blocks=block_estimate)
    except Exception as e:
        return _err("build_cylinder", e)


_POS_RX = re.compile(r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]")
_ROT_RX = re.compile(r"\[([-\d.]+)f?,\s*([-\d.]+)f?\]")


@dataclass(frozen=True)
class PlayerFacing:
    x: int
    y: int
    z: int
    yaw: float
    forward_dx: int
    forward_dz: int

    @property
    def right_dx(self) -> int:
        return -self.forward_dz

    @property
    def right_dz(self) -> int:
        return self.forward_dx

    @property
    def facing_name(self) -> str:
        return {
            (0, 1): "south",
            (-1, 0): "west",
            (0, -1): "north",
            (1, 0): "east",
        }.get((self.forward_dx, self.forward_dz), "south")

    @property
    def door_facing(self) -> str:
        # Door's `facing` is the direction the door OPENS FROM (the side a
        # player needs to be on to face the door). For a wall sitting on the
        # back of a structure facing the player, the door should face back
        # toward the player.
        return {
            "south": "north",
            "west": "east",
            "north": "south",
            "east": "west",
        }[self.facing_name]


def _player_facing(player: str) -> PlayerFacing | None:
    """Read player position and yaw, snap yaw to a cardinal forward vector.

    Minecraft yaw: 0 = south (+Z), 90 = west (-X), 180 = north (-Z),
    270 = east (+X). We snap to the nearest 90° so deterministic forward
    direction is one of (0,+1), (-1,0), (0,-1), (+1,0).
    """

    pos_out = _rcon(f"data get entity {_quote_player(player)} Pos")
    rot_out = _rcon(f"data get entity {_quote_player(player)} Rotation")
    pos_m = _POS_RX.search(pos_out or "")
    rot_m = _ROT_RX.search(rot_out or "")
    if not pos_m or not rot_m:
        return None
    px, py, pz = float(pos_m.group(1)), float(pos_m.group(2)), float(pos_m.group(3))
    yaw = float(rot_m.group(1))
    yaw_mod = (yaw % 360 + 360) % 360
    quadrant = int((yaw_mod + 45) // 90) % 4
    forward = [(0, 1), (-1, 0), (0, -1), (1, 0)][quadrant]
    return PlayerFacing(
        x=int(math.floor(px)),
        y=int(math.floor(py)),
        z=int(math.floor(pz)),
        yaw=yaw,
        forward_dx=forward[0],
        forward_dz=forward[1],
    )


def _project_forward_rect(
    facing: PlayerFacing,
    *,
    forward_start: int,
    forward_len: int,
    width: int,
    y_base: int,
    y_height: int,
) -> tuple[int, int, int, int, int, int]:
    """Project an axis-aligned rectangle in front of the player.

    ``forward_start`` is how many blocks ahead of the player the rectangle
    begins. ``width`` blocks span perpendicular to the facing. Returns the
    (x1,y1,z1,x2,y2,z2) of the fill region.
    """

    half = (width - 1) // 2
    extra = (width - 1) - half  # asymmetric when width is even
    fx, fz = facing.forward_dx, facing.forward_dz
    rx, rz = facing.right_dx, facing.right_dz
    start_x = facing.x + fx * forward_start
    start_z = facing.z + fz * forward_start
    left_x = start_x - rx * half
    left_z = start_z - rz * half
    end_x = start_x + fx * (forward_len - 1) + rx * extra
    end_z = start_z + fz * (forward_len - 1) + rz * extra
    y1 = y_base
    y2 = y_base + y_height - 1
    return (
        min(left_x, end_x),
        min(y1, y2),
        min(left_z, end_z),
        max(left_x, end_x),
        max(y1, y2),
        max(left_z, end_z),
    )


def _stair_block_for_wall(wall_block: str) -> str:
    """Pick a vanilla stair block compatible with the wall material."""

    name = (wall_block or "").lower().removeprefix("minecraft:")
    mapping = {
        "oak_planks": "oak_stairs",
        "spruce_planks": "spruce_stairs",
        "birch_planks": "birch_stairs",
        "jungle_planks": "jungle_stairs",
        "acacia_planks": "acacia_stairs",
        "dark_oak_planks": "dark_oak_stairs",
        "mangrove_planks": "mangrove_stairs",
        "cherry_planks": "cherry_stairs",
        "bamboo_planks": "bamboo_stairs",
        "crimson_planks": "crimson_stairs",
        "warped_planks": "warped_stairs",
        "stone_bricks": "stone_brick_stairs",
        "mossy_stone_bricks": "mossy_stone_brick_stairs",
        "cracked_stone_bricks": "stone_brick_stairs",
        "deepslate_bricks": "deepslate_brick_stairs",
        "deepslate_tiles": "deepslate_tile_stairs",
        "cobblestone": "cobblestone_stairs",
        "mossy_cobblestone": "mossy_cobblestone_stairs",
        "stone": "stone_stairs",
        "smooth_stone": "stone_stairs",
        "bricks": "brick_stairs",
        "nether_bricks": "nether_brick_stairs",
        "red_nether_bricks": "red_nether_brick_stairs",
        "sandstone": "sandstone_stairs",
        "smooth_sandstone": "smooth_sandstone_stairs",
        "red_sandstone": "red_sandstone_stairs",
        "prismarine": "prismarine_stairs",
        "purpur_block": "purpur_stairs",
        "quartz_block": "quartz_stairs",
        "snow_block": "oak_stairs",
        "packed_ice": "oak_stairs",
    }
    return mapping.get(name, "oak_stairs")


def _interior_stair_commands(
    *,
    x1: int,
    z1: int,
    x2: int,
    z2: int,
    y_floor: int,
    floor_height: int,
    stair_block: str,
    axis: str,
) -> list[str]:
    """Generate `floor_height` ascending stairs against a chosen inner wall.

    Stairs run +z from the back wall inward when ``axis`` is `-z` or `+z`,
    and along +x for `-x`/`+x`. Each stair block sits one above the next.
    Lays a 2-wide stair so players can walk up easily.
    """

    cmds: list[str] = []
    if floor_height < 3:
        return cmds
    if axis in ("-z", "+z"):
        # Stairs ascend +z; place them against the wall at x = x1 + 1
        stair_x_a = x1 + 1
        stair_x_b = x1 + 2 if (x2 - x1) >= 4 else x1 + 1
        base_z = z1 + 1
        facing = "south"  # stair top points away from wall
        for i in range(floor_height - 1):
            sz = base_z + i
            sy = y_floor + i
            cmds.append(
                f"setblock {stair_x_a} {sy} {sz} {stair_block}[facing={facing},half=bottom]"
            )
            if stair_x_b != stair_x_a:
                cmds.append(
                    f"setblock {stair_x_b} {sy} {sz} {stair_block}[facing={facing},half=bottom]"
                )
            # Clear the air block above the stair so the player can walk up
            cmds.append(f"setblock {stair_x_a} {sy + 1} {sz} air")
            if stair_x_b != stair_x_a:
                cmds.append(f"setblock {stair_x_b} {sy + 1} {sz} air")
    else:
        stair_z_a = z1 + 1
        stair_z_b = z1 + 2 if (z2 - z1) >= 4 else z1 + 1
        base_x = x1 + 1
        facing = "east"
        for i in range(floor_height - 1):
            sx = base_x + i
            sy = y_floor + i
            cmds.append(
                f"setblock {sx} {sy} {stair_z_a} {stair_block}[facing={facing},half=bottom]"
            )
            if stair_z_b != stair_z_a:
                cmds.append(
                    f"setblock {sx} {sy} {stair_z_b} {stair_block}[facing={facing},half=bottom]"
                )
            cmds.append(f"setblock {sx} {sy + 1} {stair_z_a} air")
            if stair_z_b != stair_z_a:
                cmds.append(f"setblock {sx} {sy + 1} {stair_z_b} air")
    return cmds


def build_house(
    center_x: int,
    y: int,
    center_z: int,
    width: int = 7,
    depth: int = 7,
    height: int = 5,
    wall_block: str = "oak_planks",
    roof_block: str = "oak_slab",
    window_block: str = "glass_pane",
    door_block: str = "oak_door",
    door_facing: str = "north",
    front_axis: str = "-z",
    floor_block: str | None = None,
    stair_block: str | None = None,
    add_floors: bool = True,
) -> ToolResult:
    """Build a rectangular house with a door, front windows, and (when tall
    enough) internal floor dividers + an interior staircase.

    For ``height >= 7``, an upper floor is laid every 4 blocks of wall height
    and a 2-wide staircase climbs against the back-left interior wall so each
    story is reachable. ``stair_block`` defaults to a wall-matching variant.
    """

    try:
        center_x, y, center_z = int(center_x), int(y), int(center_z)
        width = max(5, min(int(width), 21))
        depth = max(5, min(int(depth), 21))
        height = max(4, min(int(height), 16))

        x1 = center_x - width // 2
        x2 = x1 + width - 1
        z1 = center_z - depth // 2
        z2 = z1 + depth - 1
        roof_y = y + height
        door_y_lower = y + 1
        door_y_upper = y + 2
        window_y = y + 2

        axis = (front_axis or "-z").lower()
        if axis == "-z":
            door_pos = (center_x, z1)
            windows = [(max(x1 + 1, center_x - 2), z1), (min(x2 - 1, center_x + 2), z1)]
        elif axis == "+z":
            door_pos = (center_x, z2)
            windows = [(max(x1 + 1, center_x - 2), z2), (min(x2 - 1, center_x + 2), z2)]
        elif axis == "-x":
            door_pos = (x1, center_z)
            windows = [(x1, max(z1 + 1, center_z - 2)), (x1, min(z2 - 1, center_z + 2))]
        elif axis == "+x":
            door_pos = (x2, center_z)
            windows = [(x2, max(z1 + 1, center_z - 2)), (x2, min(z2 - 1, center_z + 2))]
        else:
            raise ValueError(f"front_axis must be one of -z|+z|-x|+x, got {front_axis!r}")

        floor_mat = floor_block or wall_block
        stair_mat = stair_block or _stair_block_for_wall(wall_block)
        story_height = 4
        # A story is a 3-block-tall room + a 1-block floor above it. We add
        # an interior floor + staircase whenever the wall is tall enough to
        # leave 2 blocks of headroom on the upper level (height >= 7).
        if add_floors and height >= 7:
            n_stories = max(2, height // story_height)
        else:
            n_stories = 1

        door_x, door_z = door_pos
        commands = [
            f"fill {x1} {y} {z1} {x2} {y + height - 1} {z2} {wall_block} hollow",
            f"fill {x1 + 1} {y + 1} {z1 + 1} {x2 - 1} {y + height - 2} {z2 - 1} air replace",
            f"fill {x1 - 1} {roof_y} {z1 - 1} {x2 + 1} {roof_y} {z2 + 1} {roof_block} replace",
            f"setblock {door_x} {door_y_lower} {door_z} air",
            f"setblock {door_x} {door_y_upper} {door_z} air",
            f"setblock {door_x} {door_y_lower} {door_z} {door_block}[facing={door_facing},half=lower]",
            f"setblock {door_x} {door_y_upper} {door_z} {door_block}[facing={door_facing},half=upper]",
            f"setblock {windows[0][0]} {window_y} {windows[0][1]} {window_block}",
            f"setblock {windows[1][0]} {window_y} {windows[1][1]} {window_block}",
        ]

        if n_stories >= 2:
            for s in range(1, n_stories):
                floor_y = y + s * story_height
                # Solid floor with a 2x2 stair landing cut at the back-left
                # corner so the staircase comes up through it.
                commands.append(
                    f"fill {x1 + 1} {floor_y} {z1 + 1} {x2 - 1} {floor_y} {z2 - 1} {floor_mat} replace"
                )
                if axis in ("-z", "+z"):
                    hole_x1, hole_x2 = x1 + 1, min(x1 + 2, x2 - 1)
                    hole_z = z1 + story_height  # the top step
                    commands.append(
                        f"fill {hole_x1} {floor_y} {z1 + 1} {hole_x2} {floor_y} {hole_z} air replace"
                    )
                else:
                    hole_z1, hole_z2 = z1 + 1, min(z1 + 2, z2 - 1)
                    hole_x = x1 + story_height
                    commands.append(
                        f"fill {x1 + 1} {floor_y} {hole_z1} {hole_x} {floor_y} {hole_z2} air replace"
                    )
                # Window on this story (light)
                if axis in ("-z", "+z"):
                    win_z = z1 if axis == "-z" else z2
                    commands.append(
                        f"setblock {center_x} {floor_y + 2} {win_z} {window_block}"
                    )
                else:
                    win_x = x1 if axis == "-x" else x2
                    commands.append(
                        f"setblock {win_x} {floor_y + 2} {center_z} {window_block}"
                    )

            # Stairs per story
            for s in range(n_stories - 1):
                base_y = y + 1 + s * story_height
                commands.extend(
                    _interior_stair_commands(
                        x1=x1,
                        z1=z1,
                        x2=x2,
                        z2=z2,
                        y_floor=base_y,
                        floor_height=story_height,
                        stair_block=stair_mat,
                        axis=axis,
                    )
                )

        out, cmds = _run_many(commands)
        return _ok("build_house", out, commands=cmds, blocks=width * depth * height)
    except Exception as e:
        return _err("build_house", e)


def build_house_at_player(
    player: str,
    width: int = 7,
    depth: int = 7,
    height: int = 5,
    distance: int = 3,
    wall_block: str = "oak_planks",
    roof_block: str = "oak_slab",
    window_block: str = "glass_pane",
    door_block: str = "oak_door",
    floor_block: str | None = None,
    stair_block: str | None = None,
    add_floors: bool = True,
) -> ToolResult:
    """Build a house in front of the player, door facing the player.

    When ``height >= 7`` the build adds interior floor dividers every 4
    blocks plus a 2-wide staircase against the back-left wall, producing
    real multi-story interiors instead of a hollow shell.
    """

    try:
        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")
        width = max(5, min(int(width), 21))
        depth = max(5, min(int(depth), 21))
        height = max(4, min(int(height), 16))
        distance = max(1, min(int(distance), 12))

        center_forward = distance + depth // 2
        center_x = facing.x + facing.forward_dx * center_forward
        center_z = facing.z + facing.forward_dz * center_forward
        y = facing.y - 1

        axis_by_facing = {"south": "-z", "west": "+x", "north": "+z", "east": "-x"}
        front_axis = axis_by_facing[facing.facing_name]

        result = build_house(
            center_x=center_x,
            y=y,
            center_z=center_z,
            width=width,
            depth=depth,
            height=height,
            wall_block=wall_block,
            roof_block=roof_block,
            window_block=window_block,
            door_block=door_block,
            door_facing=facing.door_facing,
            front_axis=front_axis,
            floor_block=floor_block,
            stair_block=stair_block,
            add_floors=add_floors,
        )
        result.tool = "build_house_at_player"
        return result
    except Exception as e:
        return _err("build_house_at_player", e)


def build_animal_pen_at_player(
    player: str,
    animal: str = "chicken",
    count: int = 4,
    width: int = 7,
    depth: int = 7,
    distance: int = 3,
    fence_block: str | None = "oak_fence",
    gate_block: str | None = "oak_fence_gate",
    floor_block: str | None = "grass_block",
    with_roof: bool = False,
    roof_block: str | None = "oak_slab",
    wall_block: str | None = "oak_planks",
    wall_height: int = 3,
) -> ToolResult:
    """Build a fenced animal pen in front of the player and summon animals.

    By default produces an open pen with a fence perimeter, a gate facing
    the player, and ``count`` animals scattered inside. Set
    ``with_roof=True`` to enclose it as a coop / barn / hutch (adds wood
    walls, a door, and a slab roof). ``animal`` must be one of the
    allowlisted vanilla peaceful mobs (chicken, pig, cow, sheep, rabbit,
    horse, goat, bee, parrot, …).
    """

    try:
        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")

        a = _normalize_entity_id(animal)
        if a not in _ANIMAL_ALLOWLIST:
            raise ValueError(
                f"animal '{a}' not in allowlist; use one of {sorted(_ANIMAL_ALLOWLIST)[:6]}…"
            )

        # LLMs sometimes pass null for optional block args; fall back to
        # sensible defaults so we never produce a "setblock x y z None"
        # command.
        fence_block = fence_block or "oak_fence"
        gate_block = gate_block or "oak_fence_gate"
        floor_block = floor_block or "grass_block"
        roof_block = roof_block or "oak_slab"
        wall_block = wall_block or "oak_planks"

        width = max(3, min(int(width), 21))
        depth = max(3, min(int(depth), 21))
        distance = max(1, min(int(distance), 12))
        n = max(1, min(int(count), 16))
        wall_height = max(2, min(int(wall_height), 6))

        center_forward = distance + depth // 2
        cx = facing.x + facing.forward_dx * center_forward
        cz = facing.z + facing.forward_dz * center_forward
        y = facing.y - 1
        half_w = width // 2
        half_d = depth // 2
        x1, z1 = cx - half_w, cz - half_d
        x2, z2 = cx + half_w, cz + half_d

        commands: list[str] = [
            # Floor.
            f"fill {x1} {y} {z1} {x2} {y} {z2} {floor_block} replace",
            # Clear the air column above the floor so animals don't suffocate.
            f"fill {x1} {y + 1} {z1} {x2} {y + wall_height + 1} {z2} air replace",
            # Fence perimeter at the floor's top edge. Do not use vanilla
            # `fill ... hollow` for a one-block-tall volume: Minecraft treats
            # that as all boundary blocks, which fills the entire pen with
            # fence posts. Four explicit sides produce a real empty corral.
            f"fill {x1} {y + 1} {z1} {x2} {y + 1} {z1} {fence_block} replace",
            f"fill {x1} {y + 1} {z2} {x2} {y + 1} {z2} {fence_block} replace",
            f"fill {x1} {y + 1} {z1} {x1} {y + 1} {z2} {fence_block} replace",
            f"fill {x2} {y + 1} {z1} {x2} {y + 1} {z2} {fence_block} replace",
        ]

        gate_axis_by_facing = {
            "south": ("z", z1),
            "north": ("z", z2),
            "west": ("x", x2),
            "east": ("x", x1),
        }
        axis, near = gate_axis_by_facing[facing.facing_name]
        if axis == "z":
            gx, gz = cx, near
        else:
            gx, gz = near, cz

        if with_roof:
            # Wooden walls on top of the fence row, then a slab roof, then
            # a door cut into the player-facing wall.
            commands.append(
                f"fill {x1} {y + 2} {z1} {x2} {y + wall_height} {z2} {wall_block} hollow"
            )
            commands.append(
                f"fill {x1 + 1} {y + 2} {z1 + 1} {x2 - 1} {y + wall_height} {z2 - 1} air replace"
            )
            commands.append(
                f"fill {x1} {y + wall_height + 1} {z1} {x2} {y + wall_height + 1} {z2} {roof_block} replace"
            )
            # Carve a 1x2 door opening through the fence + wall and place a
            # vanilla oak_door pair facing back at the player.
            commands.append(f"setblock {gx} {y + 1} {gz} air")
            commands.append(f"setblock {gx} {y + 2} {gz} air")
            commands.append(
                f"setblock {gx} {y + 1} {gz} oak_door[facing={facing.door_facing},half=lower]"
            )
            commands.append(
                f"setblock {gx} {y + 2} {gz} oak_door[facing={facing.door_facing},half=upper]"
            )
        else:
            # Open-air pen: just swap the fence at the gate location for a
            # fence gate that swings toward the player.
            commands.append(
                f"setblock {gx} {y + 1} {gz} {gate_block}[facing={facing.door_facing}]"
            )

        # Summon N animals scattered evenly across the interior.
        interior_x1 = x1 + 1
        interior_z1 = z1 + 1
        interior_w = max(1, width - 2)
        interior_d = max(1, depth - 2)
        for i in range(n):
            ax = interior_x1 + (i * 3) % interior_w
            az = interior_z1 + ((i * 5 + 1) % interior_d)
            commands.append(f"summon {a} {ax} {y + 2} {az}")

        out, cmds = _run_many(commands)
        return _ok(
            "build_animal_pen_at_player",
            out,
            commands=cmds,
            blocks=width * depth + n,
        )
    except Exception as e:
        return _err("build_animal_pen_at_player", e)


def build_castle_at_player(
    player: str,
    size: int = 15,
    height: int = 6,
    tower_height: int = 10,
    tower_size: int = 3,
    distance: int = 3,
    wall_block: str = "stone_bricks",
    floor_block: str = "stone_bricks",
    roof_block: str = "stone_brick_slab",
    door_block: str = "oak_door",
) -> ToolResult:
    """Build a small castle in front of the player.

    The castle has hollow stone-brick walls, four corner towers, alternating
    crenelations on the top wall, an open doorway on the player-facing side,
    and a solid floor. ``size`` is the outer footprint width/depth in blocks;
    ``height`` is the wall height; ``tower_height`` is how far the corner
    towers stick above the floor.
    """

    try:
        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")
        size = max(7, min(int(size), 31))
        height = max(4, min(int(height), 24))
        tower_height = max(height + 1, min(int(tower_height), height + 12))
        tower_size = max(2, min(int(tower_size), 5))
        distance = max(1, min(int(distance), 12))

        # Centre the castle in front of the player along their facing axis.
        center_forward = distance + size // 2
        cx = facing.x + facing.forward_dx * center_forward
        cz = facing.z + facing.forward_dz * center_forward
        y = facing.y - 1
        half = size // 2

        x1, z1 = cx - half, cz - half
        x2, z2 = cx + half, cz + half

        commands: list[str] = [
            # Solid floor under the courtyard.
            f"fill {x1} {y} {z1} {x2} {y} {z2} {floor_block} replace",
            # Hollow outer wall.
            f"fill {x1} {y + 1} {z1} {x2} {y + height} {z2} {wall_block} hollow",
            # Clear the inside above the floor so the courtyard is open.
            f"fill {x1 + 1} {y + 1} {z1 + 1} {x2 - 1} {y + height} {z2 - 1} air replace",
        ]

        # Four corner towers (solid base for stability, hollow above).
        ts = tower_size
        tower_offset_x = (ts - 1) // 2
        tower_offset_z = (ts - 1) // 2
        corners = [
            (x1, z1),
            (x2, z1),
            (x1, z2),
            (x2, z2),
        ]
        for tx, tz in corners:
            tx1 = tx - tower_offset_x
            tz1 = tz - tower_offset_z
            tx2 = tx1 + ts - 1
            tz2 = tz1 + ts - 1
            commands.append(
                f"fill {tx1} {y + 1} {tz1} {tx2} {y + tower_height} {tz2} {wall_block} hollow"
            )
            # Roof slab covers the tower so it doesn't look like an open chimney.
            commands.append(
                f"fill {tx1} {y + tower_height + 1} {tz1} {tx2} {y + tower_height + 1} {tz2} {roof_block} replace"
            )
            # A 3x3 hollow tower centered on the castle wall corner would
            # otherwise hollow out the shared corner column. Restore it after
            # the tower shell so the wall corner remains structural.
            commands.append(f"fill {tx} {y + 1} {tz} {tx} {y + tower_height} {tz} {wall_block} replace")

        # Crenelations: alternate wall_block / air along the top of each
        # outer wall (one block above the wall height).
        cren_y = y + height + 1
        for xi in range(x1, x2 + 1):
            block = wall_block if (xi - x1) % 2 == 0 else "air"
            commands.append(f"setblock {xi} {cren_y} {z1} {block}")
            commands.append(f"setblock {xi} {cren_y} {z2} {block}")
        for zi in range(z1 + 1, z2):
            block = wall_block if (zi - z1) % 2 == 0 else "air"
            commands.append(f"setblock {x1} {cren_y} {zi} {block}")
            commands.append(f"setblock {x2} {cren_y} {zi} {block}")

        # Doorway in the centre of the player-facing wall (1x2 air opening,
        # then place an oak_door pair facing back toward the player).
        door_axis_by_facing = {
            "south": ("z", z1),
            "north": ("z", z2),
            "west": ("x", x2),
            "east": ("x", x1),
        }
        axis, near = door_axis_by_facing[facing.facing_name]
        if axis == "z":
            dx = cx
            dz = near
        else:
            dx = near
            dz = cz
        commands.extend(
            [
                f"setblock {dx} {y + 1} {dz} air",
                f"setblock {dx} {y + 2} {dz} air",
                f"setblock {dx} {y + 1} {dz} {door_block}[facing={facing.door_facing},half=lower]",
                f"setblock {dx} {y + 2} {dz} {door_block}[facing={facing.door_facing},half=upper]",
            ]
        )

        # Interior staircase from the courtyard floor up to the wall-walk,
        # and a ladder running up one tower so the parapet is reachable.
        stair_mat = _stair_block_for_wall(wall_block)
        commands.extend(
            _interior_stair_commands(
                x1=x1,
                z1=z1,
                x2=x2,
                z2=z2,
                y_floor=y + 1,
                floor_height=height,
                stair_block=stair_mat,
                axis="-z",
            )
        )

        # Ladder inside the first corner tower so players can climb above
        # the wall-walk. Cut a 1-block air column up the inside of the tower
        # and stack ladders against an interior wall.
        ltx, ltz = corners[0]
        ladder_x = ltx + 1
        ladder_z = ltz + 1
        ladder_facing = "south"
        for ly in range(y + 1, y + tower_height + 1):
            commands.append(f"setblock {ladder_x} {ly} {ladder_z} air")
            commands.append(
                f"setblock {ladder_x} {ly} {ladder_z - 1} ladder[facing={ladder_facing}]"
            )

        out, cmds = _run_many(commands)
        return _ok(
            "build_castle_at_player",
            out,
            commands=cmds,
            blocks=size * size * height,
        )
    except Exception as e:
        return _err("build_castle_at_player", e)


def _default_rail_block_for(block: str) -> str:
    name = (block or "").lower().removeprefix("minecraft:")
    if "plank" in name or name in {"oak", "spruce", "birch"}:
        return "oak_fence"
    if "stone_brick" in name or "deepslate_brick" in name:
        return "stone_brick_wall"
    if "stone" in name or "cobble" in name:
        return "cobblestone_wall"
    if "sandstone" in name:
        return "sandstone_wall"
    if "brick" in name:
        return "brick_wall"
    if "nether" in name:
        return "nether_brick_fence"
    return "oak_fence"


def _default_support_block_for(block: str) -> str:
    name = (block or "").lower().removeprefix("minecraft:")
    if "plank" in name or name == "oak":
        return "oak_log"
    if "stone_brick" in name or "cobble" in name or "stone" in name:
        return "stone_bricks"
    if "deepslate" in name:
        return "deepslate_bricks"
    if "sandstone" in name:
        return "sandstone"
    if "brick" in name:
        return "bricks"
    return "stone_bricks"


def build_bridge_at_player(
    player: str,
    length: int = 24,
    width: int = 2,
    block: str = "oak_planks",
    distance: int = 1,
    rail_block: str | None = None,
    rail_height: int = 1,
    support_block: str | None = None,
    support_every: int = 6,
    support_drop: int = 6,
    add_supports: bool = True,
    add_rails: bool = True,
) -> ToolResult:
    """Build a horizontal bridge straight in front of the player.

    The deck sits at ``player_y - 1`` so the player can walk onto it. By
    default the bridge gets material-matched side railings and vertical
    support pillars every ``support_every`` blocks (dropping
    ``support_drop`` blocks beneath the deck) so it isn't a floating plank
    strip. Pass ``add_rails=False`` / ``add_supports=False`` for an
    intentionally bare deck.
    """

    try:
        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")
        length = max(2, min(int(length), 128))
        width = max(1, min(int(width), 8))
        distance = max(0, min(int(distance), 8))
        rail_height = max(0, min(int(rail_height), 4))
        support_every = max(2, min(int(support_every), 32))
        support_drop = max(0, min(int(support_drop), 24))

        if add_rails and not rail_block:
            rail_block = _default_rail_block_for(block)
        if not rail_block:
            rail_height = 0
        if add_supports and not support_block:
            support_block = _default_support_block_for(block)

        deck_y = facing.y - 1
        x1, y1, z1, x2, y2, z2 = _project_forward_rect(
            facing,
            forward_start=distance,
            forward_len=length,
            width=width,
            y_base=deck_y,
            y_height=1,
        )
        commands = [f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block} replace"]

        if rail_block and rail_height > 0:
            for offset in (-1, width):
                rx1, ry1, rz1, rx2, ry2, rz2 = _project_forward_rect(
                    facing,
                    forward_start=distance,
                    forward_len=length,
                    width=1,
                    y_base=deck_y + 1,
                    y_height=rail_height,
                )
                shift_x = facing.right_dx * (offset - (width - 1) // 2)
                shift_z = facing.right_dz * (offset - (width - 1) // 2)
                commands.append(
                    f"fill {rx1 + shift_x} {ry1} {rz1 + shift_z} "
                    f"{rx2 + shift_x} {ry2} {rz2 + shift_z} {rail_block} replace"
                )

        if add_supports and support_block and support_drop > 0 and length >= support_every:
            # Vertical pillars under the deck at regular intervals, dropping
            # `support_drop` blocks below the bridge. Each pillar spans the
            # full bridge width so the deck is visually carried.
            for step in range(support_every - 1, length, support_every):
                px1 = facing.x + facing.forward_dx * (distance + step)
                pz1 = facing.z + facing.forward_dz * (distance + step)
                # Stretch sideways to cover the bridge width
                sx_start = -((width - 1) // 2)
                sx_end = sx_start + width - 1
                ax = px1 + facing.right_dx * sx_start
                az = pz1 + facing.right_dz * sx_start
                bx = px1 + facing.right_dx * sx_end
                bz = pz1 + facing.right_dz * sx_end
                lo_x, hi_x = sorted((ax, bx))
                lo_z, hi_z = sorted((az, bz))
                commands.append(
                    f"fill {lo_x} {deck_y - support_drop} {lo_z} "
                    f"{hi_x} {deck_y - 1} {hi_z} {support_block} replace"
                )

        out, cmds = _run_many(commands)
        return _ok(
            "build_bridge_at_player",
            out,
            commands=cmds,
            blocks=length * width + (length * 2 * rail_height if rail_block else 0),
        )
    except Exception as e:
        return _err("build_bridge_at_player", e)


def build_wall_at_player(
    player: str,
    length: int = 16,
    height: int = 4,
    block: str = "stone_bricks",
    distance: int = 2,
) -> ToolResult:
    """Build a vertical wall directly in front of the player."""

    try:
        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")
        length = max(2, min(int(length), 64))
        height = max(1, min(int(height), 32))
        distance = max(0, min(int(distance), 8))

        x1, y1, z1, x2, y2, z2 = _project_forward_rect(
            facing,
            forward_start=distance,
            forward_len=1,
            width=length,
            y_base=facing.y,
            y_height=height,
        )
        cmd = f"fill {x1} {y1} {z1} {x2} {y2} {z2} {block} replace"
        out = _rcon(cmd, timeout=60)
        if _looks_like_mc_error(out):
            return ToolResult(
                ok=False,
                tool="build_wall_at_player",
                output=out,
                commands=[cmd],
                error=_first_line(out) or "fill failed",
            )
        return _ok("build_wall_at_player", out, commands=[cmd], blocks=length * height)
    except Exception as e:
        return _err("build_wall_at_player", e)


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
        center_x, y, center_z = int(center_x), int(y), int(center_z)
        height, radius = int(height), int(radius)
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


def _guard_fawe_volume(estimate: int, tool: str) -> None:
    if estimate > MAX_BLOCKS:
        raise ValueError(
            f"refusing FAWE operation (~{estimate:,} blocks); limit is {MAX_BLOCKS:,}"
        )


def fawe_sphere_at_player(player: str, block: str, radius: int) -> ToolResult:
    if radius < 1 or radius > 64:
        return _err("fawe_sphere_at_player", ValueError("radius must be between 1 and 64"))
    try:
        _validate_block_id(block)
        _guard_fawe_volume((2 * radius + 1) ** 3, "fawe_sphere_at_player")
    except ValueError as exc:
        return _err("fawe_sphere_at_player", exc)
    return _rename_tool(fawe_as_player(player, f"//sphere {block} {radius}"), "fawe_sphere_at_player")


def fawe_cyl_at_player(
    player: str,
    block: str,
    radius: int,
    height: int,
    hollow: bool = False,
) -> ToolResult:
    if radius < 1 or radius > 64:
        return _err("fawe_cyl_at_player", ValueError("radius must be between 1 and 64"))
    if height < 1 or height > 256:
        return _err("fawe_cyl_at_player", ValueError("height must be between 1 and 256"))
    try:
        _validate_block_id(block)
        _guard_fawe_volume((2 * radius + 1) ** 2 * height, "fawe_cyl_at_player")
    except ValueError as exc:
        return _err("fawe_cyl_at_player", exc)
    flag = " -h" if hollow else ""
    return _rename_tool(
        fawe_as_player(player, f"//cyl{flag} {block} {radius} {height}"),
        "fawe_cyl_at_player",
    )


def mine_shaft_at_player(
    player: str,
    depth: int = 32,
    radius: int = 0,
    forward_offset: int = 0,
) -> ToolResult:
    """Dig a vertical shaft beneath the player.

    Uses vanilla ``execute as <player> at @s [positioned ^ ^ ^F] run fill`` because
    FAWE ``//cyl`` expands *upward* from its selection origin — the wrong
    direction for "drill below me" and a previous source of bugs (silent
    upward column with the shaft sitting in the sky).

    Args:
        player: Player name. Bedrock names keep the leading dot.
        depth: Blocks of vertical shaft to clear (clamped to 1..256).
        radius: Half-width of the shaft (0..5). 0 → 1x1 column, 1 → 3x3,
            etc. Picked to stay below the vanilla fill cap of 32768 blocks.
        forward_offset: Blocks ahead of the player's facing the shaft is
            placed. 0 = directly below the player; positive = forward;
            negative = behind. Uses caret-local coordinates so it respects
            yaw without needing to compute it on the host.
    """

    try:
        depth_i = max(1, min(int(depth), 256))
        radius_i = max(0, min(int(radius), 5))
        forward_i = max(-16, min(int(forward_offset), 16))

        def _rel(off: int) -> str:
            if off == 0:
                return "~"
            return f"~{off}" if off > 0 else f"~{off}"

        neg_r = _rel(-radius_i)
        pos_r = _rel(radius_i)
        prefix = f"execute as {_quote_player(player)} at @s"
        if forward_i != 0:
            prefix += f" positioned ^ ^ ^{forward_i}"
        cmd = (
            f"{prefix} run fill "
            f"{neg_r} ~-1 {neg_r} "
            f"{pos_r} ~-{depth_i} {pos_r} "
            f"air replace"
        )
        out = _rcon(cmd, timeout=60)
        if _looks_like_mc_error(out):
            return ToolResult(
                ok=False,
                tool="mine_shaft_at_player",
                output=out,
                commands=[cmd],
                error=_first_line(out) or "fill failed",
            )
        blocks = (2 * radius_i + 1) ** 2 * depth_i
        return _ok("mine_shaft_at_player", out, commands=[cmd], blocks=blocks)
    except Exception as e:
        return _err("mine_shaft_at_player", e)


def list_templates(
    category: str | None = None,
    tags: list[str] | None = None,
) -> ToolResult:
    """List curated build templates from the catalog."""

    try:
        items = template_catalog.list_template_summaries(category=category, tags=tags)
        lines = [f"{t['id']}: {t['title']} ({t['category']})" for t in items]
        text = f"{len(items)} template(s)\n" + "\n".join(lines)
        return _ok("list_templates", text, commands=[])
    except Exception as e:
        return _err("list_templates", e)


def search_templates(
    query: str,
    *,
    category: str | None = None,
    intent_family: str = "",
) -> ToolResult:
    """Rank templates for a natural-language query (hybrid lexical + semantic)."""

    try:
        from agent.templates.ranking import resolve_template

        ranked = resolve_template(query, category=category, intent_family=intent_family)
        if not ranked.top_candidates:
            return _ok(
                "search_templates",
                f"No matches for: {query!r}",
                commands=[],
            )
        lines = [
            f"confidence={ranked.confidence} ({ranked.confidence_score:.2f})",
            f"selected={ranked.selected_template_id or '(none)'}",
        ]
        if ranked.disambiguation_message:
            lines.append(ranked.disambiguation_message)
        lines.append("candidates:")
        for c in ranked.top_candidates[:5]:
            meta = template_catalog.find_template(c.template_id)
            lines.append(
                f"  - {meta.title} [{c.template_id}] "
                f"score={c.total:.3f} lex={c.lexical:.2f} sem={c.semantic:.2f} "
                f"pol={c.policy:.2f} reasons={','.join(c.reasons) or '-'}"
            )
        return _ok("search_templates", "\n".join(lines), commands=[])
    except Exception as e:
        return _err("search_templates", e)


def _template_follow_up_steps(
    meta: template_catalog.TemplateMeta,
    *,
    player: str,
    ax: int,
    ay: int,
    az: int,
) -> tuple[list[str], list[str]]:
    """Run catalog follow_up steps (e.g. summon animals after paste/fallback)."""

    follow_msgs: list[str] = []
    commands: list[str] = []
    for step in meta.follow_up:
        stool = str(step.get("tool") or "")
        if stool == "summon_entity":
            ent = str(step.get("entity") or "chicken")
            cnt = int(step.get("count") or 1)
            oy_off = int(step.get("offset_y") or 1)
            sr = summon_entity(ent, ax, ay + oy_off, az, count=cnt)
            follow_msgs.append(sr.output or sr.error or "")
            commands.extend(sr.commands)
        elif stool:
            fn = _tool_dispatch().get(stool)
            if fn:
                sargs = {k: v for k, v in step.items() if k != "tool"}
                if "player" not in sargs:
                    sargs["player"] = player
                sr = fn(**sargs)
                follow_msgs.append(sr.output or sr.error or "")
                commands.extend(sr.commands)
    return follow_msgs, commands


def paste_template_at_player(
    player: str,
    template_id: str,
    distance: int | None = None,
    rotation: int = 0,
    mirror: str | None = None,
    adapt_palette: bool = False,
) -> ToolResult:
    """Paste a catalog schematic in front of the player (FAWE), with parametric fallback.

    Loads ``//schem load neighborhood/<id>`` and pastes at an anchor in front of
    the player. If the ``.schem`` file is not on the server yet, runs the catalog's
    ``fallback`` tool (e.g. ``build_animal_pen_at_player``) instead.
    """

    try:
        from agent.routing_context import note_template_provenance

        # Accept either a real id or free-text. Resolve fuzzy first so the
        # tool is usable from natural language without anyone — user or LLM —
        # having to know the snake_case canonical id.
        from agent.routing_context import note_template_ranking
        from agent.templates.ranking import resolve_template

        raw = (template_id or "").strip()
        ranked = resolve_template(raw)
        note_template_ranking(ranked)
        resolved = ranked.selected_template_id or template_catalog.resolve_template_id(raw) or raw
        try:
            meta = template_catalog.find_template(resolved)
        except ValueError:
            # The id couldn't be resolved (LLM hallucinated something like
            # "sand fort"). Return a structured error with concrete suggestions
            # so the next tool call has somewhere to go.
            top_alts = [c.template_id for c in ranked.top_candidates[:3]]
            suggest = ", ".join(top_alts) if top_alts else "list_templates"
            hint = (
                f"unknown template_id {raw!r}; closest matches: {suggest}. "
                "If the player named a material (sand, stone, wood) plus a "
                "structure (fort, house, castle), prefer build_house_at_player "
                "or build_castle_at_player with the matching wall_block."
            )
            return ToolResult(
                ok=False,
                tool="paste_template_at_player",
                error=hint,
                output="",
                commands=[],
            )
        note_template_provenance(meta.id)
        # We intentionally do NOT splice ranked.disambiguation_message into
        # the successful paste output. The LLM tends to parrot it verbatim
        # ("Did you mean …?") which confuses players who already got what
        # they asked for. Alternatives stay reachable via `search_templates`.
        rank_note = ""
        if ranked.confidence == "low":
            alts = ", ".join(
                template_catalog.find_template(c.template_id).title
                for c in ranked.top_candidates[:3]
                if c.template_id != meta.id
            )
            if alts:
                rank_note = f"\n(also consider: {alts})"
        dist = meta.distance_default if distance is None else max(1, min(int(distance), 16))
        vol = meta.footprint_volume()
        if vol > meta.max_blocks:
            raise ValueError(
                f"template {meta.id} footprint {vol:,} exceeds catalog max_blocks {meta.max_blocks:,}"
            )
        if vol > MAX_BLOCKS:
            raise ValueError(
                f"template {meta.id} footprint {vol:,} exceeds global limit {MAX_BLOCKS:,}"
            )

        facing = _player_facing(player)
        if facing is None:
            raise RuntimeError(f"could not read facing for {player}")

        center_forward = dist + max(meta.footprint[2], meta.footprint[0]) // 2
        ax = facing.x + facing.forward_dx * center_forward
        ay = facing.y - 1
        az = facing.z + facing.forward_dz * center_forward

        on_server = template_catalog.schematic_available_on_server(meta)
        if not on_server:
            template_catalog.ensure_schematic_on_server(meta)
            on_server = template_catalog.schematic_available_on_server(meta)

        commands: list[str] = []

        if not on_server:
            from agent.routing_context import current_routing
            from agent.templates.anchor import resolve_step_args

            rec = current_routing()
            if rec:
                rec.fallback_reason = "schematic_missing"

            if meta.fallback_steps:
                parts: list[str] = []
                all_cmds: list[str] = []
                last_result: ToolResult | None = None
                for step in meta.fallback_steps:
                    stool = str(step.get("tool") or "")
                    sargs = resolve_step_args(
                        dict(step.get("args") or {}), ax=ax, ay=ay, az=az
                    )
                    sargs.setdefault("player", player)
                    fn = _tool_dispatch().get(stool)
                    if fn is None:
                        raise ValueError(f"fallback_steps tool not found: {stool}")
                    last_result = fn(**sargs)
                    if not last_result.ok:
                        return last_result
                    parts.append(last_result.output or "")
                    all_cmds.extend(last_result.commands)
                assert last_result is not None
                follow_msgs, follow_cmds = _template_follow_up_steps(
                    meta, player=player, ax=ax, ay=ay, az=az
                )
                last_result.tool = "paste_template_at_player"
                last_result.output = (
                    "schematic unavailable; used fallback_steps\n" + "\n".join(parts)
                )
                if follow_msgs:
                    last_result.output += "\n" + "\n".join(follow_msgs)
                last_result.commands = all_cmds + follow_cmds
                if rank_note:
                    last_result.output = (last_result.output or "") + rank_note
                return last_result

            if not meta.fallback:
                raise FileNotFoundError(
                    f"schematic missing for {meta.id} and no fallback defined"
                )
            fb = meta.fallback
            fb_tool = str(fb.get("tool") or "")
            fb_args = resolve_step_args(dict(fb.get("args") or {}), ax=ax, ay=ay, az=az)
            fb_args.setdefault("player", player)
            fn = _tool_dispatch().get(fb_tool)
            if fn is None:
                raise ValueError(f"fallback tool not found: {fb_tool}")
            result = fn(**fb_args)
            follow_msgs, follow_cmds = _template_follow_up_steps(
                meta, player=player, ax=ax, ay=ay, az=az
            )
            result.tool = "paste_template_at_player"
            prefix = f"schematic unavailable; used fallback {fb_tool}\n"
            result.output = prefix + (result.output or "")
            if follow_msgs:
                result.output += "\n" + "\n".join(follow_msgs)
            if rank_note:
                result.output += rank_note
            result.commands = list(result.commands) + follow_cmds
            return result

        # Save position, paste at anchor, restore.
        pos_out = _rcon(f"data get entity {_quote_player(player)} Pos")
        pos_m = _POS_RX.search(pos_out or "")
        if not pos_m:
            raise RuntimeError("could not read player position for paste anchor")
        ox, oy, oz = float(pos_m.group(1)), float(pos_m.group(2)), float(pos_m.group(3))

        commands.append(f"tp {_quote_player(player)} {ax} {ay} {az}")
        load_name = meta.schematic_load_name
        commands.append(f"agentexec {_quote_player(player)} //schem load {load_name}")

        paste_flags = "-a"
        if rotation:
            paste_flags += f" -r {int(rotation) % 360}"
        if mirror:
            m = mirror.strip().lower()
            if m in ("x", "z", "xz"):
                paste_flags += f" -m {m}"
        commands.append(f"agentexec {_quote_player(player)} //paste {paste_flags}")

        if adapt_palette:
            commands.append(
                f"agentexec {_quote_player(player)} //replace oak_planks spruce_planks"
            )

        commands.append(
            f"tp {_quote_player(player)} {int(math.floor(ox))} {int(math.floor(oy))} {int(math.floor(oz))}"
        )

        out_parts: list[str] = []
        for cmd in commands:
            out = _rcon(cmd, timeout=60)
            if _looks_like_mc_error(out):
                raise RuntimeError(f"{_first_line(out)} while running: {cmd}")
            out_parts.append(out)

        follow_msgs, follow_cmds = _template_follow_up_steps(
            meta, player=player, ax=ax, ay=ay, az=az
        )
        commands.extend(follow_cmds)

        text = (
            f"pasted template {meta.id} at ({ax}, {ay}, {az})\n"
            + "\n".join(o for o in out_parts if o)
        )
        if follow_msgs:
            text += "\n" + "\n".join(follow_msgs)
        if rank_note:
            text += rank_note
        return _ok("paste_template_at_player", text, commands=commands, blocks=vol)
    except Exception as e:
        return _err("paste_template_at_player", e)


def create_template_from_selection(
    player: str,
    template_id: str,
    overwrite: bool = False,
    tags: list[str] | None = None,
) -> ToolResult:
    """Save the player's current FAWE selection as a new catalog schematic.

    The player must already have a WorldEdit selection (``//pos1`` / ``//pos2`` or
    wand). Writes ``agent/templates/schematics/<file>`` via docker copy from the
    server and appends metadata to ``catalog.json`` when ``overwrite`` is false.
    """

    try:
        tid = template_catalog.normalize_template_id(template_id)
        try:
            meta = template_catalog.find_template(tid)
            if template_catalog.schematic_repo_path(meta).is_file() and not overwrite:
                raise FileExistsError(
                    f"template {tid} already exists; pass overwrite=true to replace"
                )
        except ValueError:
            meta = template_catalog.register_template_entry(
                tid,
                tags=tags or [],
                overwrite=overwrite,
            )

        save_name = meta.schematic_load_name
        commands = [
            f"agentexec {_quote_player(player)} //copy",
            f"agentexec {_quote_player(player)} //schem save {save_name}",
        ]
        out_parts: list[str] = []
        for cmd in commands:
            out = _rcon(cmd, timeout=90)
            if _looks_like_mc_error(out):
                raise RuntimeError(f"{_first_line(out)} while running: {cmd}")
            out_parts.append(out)

        # Pull schematic from server into repo (best-effort).
        template_catalog.ensure_schematic_on_server(meta)
        remote = template_catalog.server_schematic_path(meta)
        local = template_catalog.schematic_repo_path(meta)
        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                ["docker", "cp", f"{CONTAINER}:{remote}", str(local)],
                capture_output=True,
                timeout=60,
            )
            if proc.returncode != 0:
                out_parts.append(
                    "note: schematic saved on server; docker cp to repo failed "
                    "(run publish script or mount schematics volume)"
                )
        except OSError as e:
            out_parts.append(f"note: could not docker cp schematic: {e}")

        tag_note = f" tags={tags}" if tags else ""
        text = f"saved template {tid} as {save_name}{tag_note}\n" + "\n".join(out_parts)
        return _ok("create_template_from_selection", text, commands=commands)
    except Exception as e:
        return _err("create_template_from_selection", e)


# FAWE primitive tools (MCP Core v1)
from agent.fawe_tools import (  # noqa: E402
    contract_selection,
    copy_selection,
    cut_selection,
    expand_selection,
    faces_in_selection,
    flip_selection,
    generate_forest_at_player,
    generate_pyramid_at_player,
    hollow_selection,
    move_selection,
    naturalize_selection,
    overlay_selection,
    paste_selection_at_player,
    redo,
    replace_in_selection,
    rotate_selection,
    select_around_player,
    select_box,
    selection_size,
    set_selection,
    smooth_selection,
    stack_selection,
    undo,
    walls_in_selection,
)


def _tool_dispatch() -> dict[str, Any]:
    from agent.tools import TOOL_DISPATCH

    return TOOL_DISPATCH


def _dispatch_entry(fn: Any) -> Any:
    """Return a kwargs-safe wrapper that ignores unknown LLM arguments."""

    import inspect

    sig = inspect.signature(fn)
    params = sig.parameters

    def _wrapped(**kwargs: Any) -> ToolResult:
        filtered = {k: v for k, v in kwargs.items() if k in params}
        return fn(**filtered)

    return _wrapped
