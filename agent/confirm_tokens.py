"""Destructive-action confirmation tokens with TTL and binding."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

CONFIRM_TTL_SEC = float(os.environ.get("AGENT_CONFIRM_TTL_SEC", "60"))


@dataclass
class PendingConfirm:
    player: str
    prompt_hash: str
    tool: str
    args_hash: str
    expires_at: float


_pending: dict[str, PendingConfirm] = {}


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [tok for tok, row in _pending.items() if row.expires_at <= now]
    for tok in expired:
        del _pending[tok]


def issue_confirm_token(
    *,
    player: str,
    prompt: str,
    tool: str,
    arguments: dict[str, Any],
    token: str,
) -> None:
    _purge_expired()
    _pending[token] = PendingConfirm(
        player=player,
        prompt_hash=_hash_text(prompt.strip()),
        tool=tool,
        args_hash=_hash_text(json.dumps(arguments, sort_keys=True)),
        expires_at=time.monotonic() + CONFIRM_TTL_SEC,
    )


def consume_confirm_token(
    *,
    token: str,
    player: str,
    prompt: str,
    tool: str,
    arguments: dict[str, Any],
) -> bool:
    """Return True if token is valid for this player/tool/args/prompt."""

    _purge_expired()
    row = _pending.get(token)
    if row is None:
        return False
    if row.player != player:
        return False
    if row.prompt_hash != _hash_text(prompt.strip()):
        return False
    if row.tool != tool:
        return False
    if row.args_hash != _hash_text(json.dumps(arguments, sort_keys=True)):
        return False
    del _pending[token]
    return True


def pending_count() -> int:
    _purge_expired()
    return len(_pending)
