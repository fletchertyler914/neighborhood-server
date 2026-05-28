"""Safety guardrails for in-game agent and MCP tool execution."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Per-player cooldown between /agent jobs (seconds).
AGENT_COOLDOWN_SEC = float(os.environ.get("AGENT_COOLDOWN_SEC", "8"))
MAX_AGENT_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "12"))

# Commands that always require confirm_token when run via run_command / fawe.
DESTRUCTIVE_PATTERNS = [
    re.compile(r"//regen\b", re.I),
    re.compile(r"//set\s+air\b", re.I),
    re.compile(r"//replace\b", re.I),
    re.compile(r"\bclear_box\b"),
    re.compile(r"\bfill\b.*\bair\b", re.I),
    re.compile(r"\bstop\b", re.I),
    re.compile(r"\bwhitelist\s+(off|disable)\b", re.I),
]

# Raw RCON denylist (server-wide danger).
RCON_DENYLIST = [
    re.compile(r"^\s*stop\b", re.I),
    re.compile(r"^\s*restart\b", re.I),
    re.compile(r"^\s*ban-ip\b", re.I),
]

# Raw RCON allowlist prefix — if set non-empty, only these prefixes pass (optional strict mode).
RCON_ALLOWLIST_PREFIXES: list[str] = os.environ.get("AGENT_RCON_ALLOWLIST", "").split(",")
RCON_ALLOWLIST_PREFIXES = [p.strip() for p in RCON_ALLOWLIST_PREFIXES if p.strip()]

_last_job_by_player: dict[str, float] = {}


@dataclass
class AuditEntry:
    timestamp: str
    player: str
    uuid: str
    prompt: str
    status: str
    model: str
    steps: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""
    dry_run: bool = False
    job_id: str | None = None
    routing: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "player": self.player,
            "uuid": self.uuid,
            "prompt": self.prompt,
            "status": self.status,
            "model": self.model,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "message": self.message,
            "dry_run": self.dry_run,
        }
        if self.routing:
            payload["routing"] = self.routing
        return json.dumps(payload, ensure_ascii=False)


def audit_log_path() -> Path:
    root = Path(os.environ.get("NEIGHBORHOOD_REPO", Path(__file__).resolve().parents[1]))
    log_dir = root / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "agent-audit.log"


def append_audit(entry: AuditEntry) -> None:
    path = audit_log_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.to_json() + "\n")


def check_cooldown(player_uuid: str) -> str | None:
    now = time.monotonic()
    last = _last_job_by_player.get(player_uuid, 0.0)
    elapsed = now - last
    if elapsed < AGENT_COOLDOWN_SEC:
        wait = AGENT_COOLDOWN_SEC - elapsed
        return f"Please wait {wait:.0f}s before another /agent request."
    _last_job_by_player[player_uuid] = now
    return None


def is_destructive_tool(tool_name: str, arguments: dict[str, Any]) -> bool:
    blob = f"{tool_name} {json.dumps(arguments)}"
    return any(p.search(blob) for p in DESTRUCTIVE_PATTERNS)


def require_confirmation(
    tool_name: str,
    arguments: dict[str, Any],
    confirm_token: str | None,
    expected_token: str | None,
) -> None:
    if not is_destructive_tool(tool_name, arguments):
        return
    if not confirm_token or not expected_token or confirm_token != expected_token:
        raise PermissionError(
            "destructive operation requires confirm_token. "
            "Re-run with: /agent confirm <token> <your prompt>"
        )


def guard_rcon_command(command: str) -> None:
    command = command.lstrip("/").strip()
    for pat in RCON_DENYLIST:
        if pat.search(command):
            raise PermissionError(f"RCON command blocked by policy: {command.split()[0]}")
    if RCON_ALLOWLIST_PREFIXES:
        if not any(command.startswith(p) for p in RCON_ALLOWLIST_PREFIXES):
            raise PermissionError(
                f"RCON command not on allowlist: {command.split()[0] if command else command}"
            )


def new_confirm_token() -> str:
    import secrets

    return secrets.token_hex(4)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
