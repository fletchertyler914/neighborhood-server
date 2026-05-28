#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi>=0.115.0",
#   "uvicorn>=0.32.0",
#   "httpx>=0.27.0",
#   "pydantic>=2.9.0",
# ]
# ///
"""Host orchestrator: /agent jobs via local Ollama with optional cloud fallback."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent.job import JobRequest, build_user_message

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agent import tools as T
from agent.context import gather as gather_context
from agent.retrieval import render_block as render_kb_block
from agent.feedback import (
    ParsedRating,
    get_last_job,
    parse_rating_prompt,
    record_feedback,
    remember_last_job,
)
from agent.confirm_tokens import consume_confirm_token, issue_confirm_token
from agent.job_store import JobStore
from agent.safety import (
    MAX_AGENT_STEPS,
    append_audit,
    audit_log_path,
    check_cooldown,
    new_confirm_token,
    requires_confirmation,
    utc_now_iso,
    AuditEntry,
)
from agent.routing_context import (
    RoutingRecord,
    current_routing,
    finish_job,
    note_template_provenance,
    set_current_job,
    start_job,
)
from agent.schema import TOOL_SCHEMAS
from agent.templates import catalog as template_catalog

EVAL_MODE = os.environ.get("AGENT_EVAL_MODE", "").strip() not in ("", "0", "false", "False")
_API_TOKEN_RAW = os.environ.get("AGENT_API_TOKEN", "").strip()
if not _API_TOKEN_RAW and not EVAL_MODE:
    raise RuntimeError(
        "AGENT_API_TOKEN must be set when AGENT_EVAL_MODE is off "
        "(use dev-change-me only for local eval)"
    )
API_TOKEN = _API_TOKEN_RAW or "dev-change-me"
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b-instruct")
CLOUD_BASE = os.environ.get("CLOUD_BASE_URL", "https://api.openai.com/v1").rstrip("/")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
JOB_TIMEOUT = int(os.environ.get("AGENT_JOB_TIMEOUT_SEC", "180"))
LOCAL_MODEL_TIMEOUT = float(os.environ.get("AGENT_LOCAL_MODEL_TIMEOUT_SEC", "20"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "512"))
BIND_HOST = os.environ.get("AGENT_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("AGENT_BIND_PORT", "8787"))
EVAL_MODEL = os.environ.get("AGENT_EVAL_MODEL", "").strip()
EVAL_DISABLE_RETRIEVAL = os.environ.get("AGENT_EVAL_DISABLE_RETRIEVAL", "").strip() not in (
    "",
    "0",
    "false",
    "False",
)
EVAL_DISABLE_DYNAMIC_CONTEXT = os.environ.get(
    "AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT", ""
).strip() not in ("", "0", "false", "False")
EVAL_LOCAL_MODEL_TIMEOUT = float(
    os.environ.get("AGENT_EVAL_LOCAL_MODEL_TIMEOUT_SEC", str(LOCAL_MODEL_TIMEOUT))
)
EVAL_NUM_CTX = int(os.environ.get("AGENT_EVAL_NUM_CTX", str(OLLAMA_NUM_CTX)))
EVAL_NUM_PREDICT = int(os.environ.get("AGENT_EVAL_NUM_PREDICT", str(OLLAMA_NUM_PREDICT)))
# When true, append "Rate this: /agent good · /agent bad <why>" to successful
# job messages so players learn the feedback feature. Off by default in eval
# / API mode; on by default in production chat.
ASK_FEEDBACK = os.environ.get("AGENT_ASK_FEEDBACK", "1").strip() not in (
    "0",
    "false",
    "False",
    "",
)
FEEDBACK_HINT = " · Rate: /agent good or /agent bad <why>"

SYSTEM_PROMPT = (_REPO / "agent" / "prompts" / "system.md").read_text(encoding="utf-8")

app = FastAPI(title="Neighborhood Minecraft Agent", version="1.0.0")

class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str = ""
    confirm_token: str | None = None
    needs_confirm: bool = False
    steps: int = 0
    model: str = ""
    tool_calls: list[dict[str, Any]] = []


@dataclass
class Job:
    id: str
    request: JobRequest
    status: JobStatus = JobStatus.queued
    message: str = ""
    steps: int = 0
    model: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


_jobs = JobStore[Job]()


def _auth(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(403, "invalid token")


_THINKING_FAMILIES = ("qwen3", "qwen3.5", "qwen3.6", "deepseek-r1", "qwq")


def _is_thinking_model(model: str) -> bool:
    m = model.lower()
    return any(f in m for f in _THINKING_FAMILIES)


async def _chat_completion(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    api_key: str | None = None,
    timeout: float | None = None,
    eval_mode: bool = False,
) -> dict[str, Any]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{base_url}/chat/completions"
    is_ollama = "11434" in base_url or base_url.endswith("ollama")
    if is_ollama:
        url = f"{base_url}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.0 if eval_mode else 0.2,
    }
    if is_ollama:
        payload["options"] = {
            "num_ctx": EVAL_NUM_CTX if eval_mode else OLLAMA_NUM_CTX,
            "num_predict": EVAL_NUM_PREDICT if eval_mode else OLLAMA_NUM_PREDICT,
        }
    if is_ollama and _is_thinking_model(model):
        payload["think"] = False
    resp = await client.post(url, headers=headers, json=payload, timeout=timeout or JOB_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _parse_tool_calls(choice: dict[str, Any]) -> list[dict[str, Any]]:
    msg = choice.get("message", {})
    calls = msg.get("tool_calls") or []
    out: list[dict[str, Any]] = []
    for call in calls:
        fn = call.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append({"id": call.get("id", name), "name": name, "arguments": args})
    return out


def _is_eval_request(req: JobRequest) -> bool:
    return EVAL_MODE or req.eval_mode


_BRIDGE_KEYWORDS = (
    "bridge",
    "walkway",
    "plank a path",
    "plank path",
    "path across",
    "cross the water",
    "across the water",
    "across the gap",
)
_HOUSE_KEYWORDS = ("house", "cabin", "shack", "hut", "fort", "shed")
_WALL_KEYWORDS = ("wall in front", "block off")
_CASTLE_KEYWORDS = ("castle", "fortress", "keep", "citadel", "stronghold")
# Animal-enclosure phrasing: a structure-type word ("coop", "pen", …)
# combined with one of the animal nouns below routes to
# build_animal_pen_at_player.
_PEN_STRUCTURE_KEYWORDS = (
    "coop",
    "pen",
    "hutch",
    "sty",
    "stable",
    "barn",
    "corral",
    "enclosure",
    "paddock",
    "fenced area",
    "fenced in area",
    "fenced-in area",
    "animal area",
)
_PEN_ANIMAL_NOUNS: tuple[tuple[str, str, bool], ...] = (
    # (prompt substring, canonical animal id, default with_roof)
    ("chicken", "chicken", True),
    ("hen", "chicken", True),
    ("rooster", "chicken", True),
    ("pig", "pig", False),
    ("hog", "pig", False),
    ("cow", "cow", False),
    ("cattle", "cow", False),
    ("bull", "cow", False),
    ("calf", "cow", False),
    ("sheep", "sheep", False),
    ("lamb", "sheep", False),
    ("rabbit", "rabbit", True),
    ("bunny", "rabbit", True),
    ("horse", "horse", True),
    ("pony", "horse", True),
    ("donkey", "donkey", True),
    ("mule", "mule", True),
    ("llama", "llama", False),
    ("goat", "goat", False),
    ("bee", "bee", False),
    ("parrot", "parrot", True),
    ("fox", "fox", False),
    ("wolf", "wolf", False),
    ("dog", "wolf", False),
    ("cat", "cat", True),
    ("kitten", "cat", True),
    ("turtle", "turtle", False),
    ("frog", "frog", False),
    ("axolotl", "axolotl", False),
)
# "give me a <thing>" intents. Used to detect when the model picked a non-item
# tool (give_haste, fawe_as_player) for an item-giving prompt.
_GIVE_KEYWORDS = (
    "give me",
    "gimme",
    "hand me",
    "i need a ",
    "i want a ",
    "spawn me",
    "drop me",
)
# Heuristic mapping of what the user said → canonical Minecraft item id.
_GIVE_ITEM_HINTS: tuple[tuple[str, str], ...] = (
    ("diamond pickaxe", "diamond_pickaxe"),
    ("diamond picaxe", "diamond_pickaxe"),
    ("netherite pickaxe", "netherite_pickaxe"),
    ("iron pickaxe", "iron_pickaxe"),
    ("golden pickaxe", "golden_pickaxe"),
    ("stone pickaxe", "stone_pickaxe"),
    ("wood pickaxe", "wooden_pickaxe"),
    ("wooden pickaxe", "wooden_pickaxe"),
    ("pickaxe", "diamond_pickaxe"),
    ("picaxe", "diamond_pickaxe"),
    ("diamond sword", "diamond_sword"),
    ("netherite sword", "netherite_sword"),
    ("iron sword", "iron_sword"),
    ("sword", "diamond_sword"),
    ("diamond axe", "diamond_axe"),
    ("axe", "diamond_axe"),
    ("diamond shovel", "diamond_shovel"),
    ("shovel", "diamond_shovel"),
    ("elytra", "elytra"),
    ("totem", "totem_of_undying"),
    ("ender pearl", "ender_pearl"),
    ("torch", "torch"),
    ("flint and steel", "flint_and_steel"),
    ("bow", "bow"),
    ("crossbow", "crossbow"),
    ("trident", "trident"),
    ("shield", "shield"),
    ("diamond armor", "diamond_chestplate"),
    ("netherite armor", "netherite_chestplate"),
    ("armor", "diamond_chestplate"),
    ("armour", "diamond_chestplate"),
)


def _looks_like_bridge_prompt(prompt: str) -> bool:
    return any(kw in prompt for kw in _BRIDGE_KEYWORDS)


def _looks_like_house_prompt(prompt: str) -> bool:
    return any(kw in prompt for kw in _HOUSE_KEYWORDS)


def _looks_like_castle_prompt(prompt: str) -> bool:
    return any(kw in prompt for kw in _CASTLE_KEYWORDS)


def _infer_animal_from_prompt(prompt: str) -> tuple[str, bool] | None:
    """Return (animal_id, default_with_roof) if the prompt names an animal."""

    for token, animal, with_roof in _PEN_ANIMAL_NOUNS:
        if token in prompt:
            return animal, with_roof
    return None


def _looks_like_animal_pen_prompt(prompt: str) -> bool:
    """A prompt like 'chicken coop', 'fenced area with chickens', etc."""

    has_structure = any(kw in prompt for kw in _PEN_STRUCTURE_KEYWORDS)
    has_animal = _infer_animal_from_prompt(prompt) is not None
    if has_structure and has_animal:
        return True
    # Compound nouns like "chicken coop" still match has_structure+has_animal,
    # but allow phrasing like "make me a coop" / "build a hutch" too — those
    # imply chickens / rabbits respectively without naming them.
    if "coop" in prompt or "hen house" in prompt:
        return True
    if "hutch" in prompt:
        return True
    return False


def _infer_pen_count_from_prompt(prompt: str) -> int | None:
    """Pull '<N> chickens' style counts out of a pen prompt."""

    m = re.search(
        r"(\d{1,2})\s+(?:chickens?|hens?|pigs?|hogs?|cows?|cattle|sheeps?|lambs?|"
        r"rabbits?|bunnies?|bunny|horses?|ponies?|pony|donkeys?|mules?|llamas?|"
        r"goats?|bees?|parrots?|foxes?|wolves|wolfs?|dogs?|cats?|kittens?|"
        r"turtles?|frogs?|axolotls?)",
        prompt,
    )
    if m:
        try:
            return max(1, min(int(m.group(1)), 16))
        except ValueError:
            return None
    if "with a bunch" in prompt or "lots of" in prompt:
        return 8
    return None


def _wants_pen_roof(prompt: str) -> bool:
    """Closed / covered phrasing wins over the animal-specific default."""

    if any(w in prompt for w in ("coop", "barn", "hutch", "stable", "hen house")):
        return True
    if any(w in prompt for w in ("paddock", "corral", "open pen", "open-air")):
        return False
    return False


def _looks_like_give_item_prompt(prompt: str) -> bool:
    if not any(kw in prompt for kw in _GIVE_KEYWORDS):
        return False
    # Only treat as a give-item prompt when an item word is present.
    if any(hint[0] in prompt for hint in _GIVE_ITEM_HINTS):
        return True
    # Generic item words that aren't haste / effects.
    return any(
        word in prompt
        for word in (
            "block",
            "blocks",
            "diamond",
            "netherite",
            "iron",
            "gold",
            "stone",
            "wood",
            "oak",
            "spruce",
            "birch",
            "stack",
        )
    )


_GIVE_NOUN_RX = re.compile(
    r"(?:give me|gimme|hand me|spawn me|drop me|i need|i want)"
    r"\s+(?:a\s+|some\s+|the\s+|stack(?:\s+of)?\s+|few\s+)?"
    r"(?:stack\s+of\s+)?"
    r"([a-z][a-z0-9_]{1,32}(?:\s+[a-z0-9_]{1,32})?)",
    re.I,
)

# Words that look like nouns but are NOT items (so we don't accidentally
# /give a player "haste" or "permission").
_GIVE_NOUN_DENY: frozenset[str] = frozenset(
    {
        "haste",
        "speed",
        "permission",
        "op",
        "creative",
        "survival",
        "spectator",
        "adventure",
        "command_block",
    }
)


def _infer_item_from_prompt(prompt: str) -> str | None:
    for token, item in _GIVE_ITEM_HINTS:
        if token in prompt:
            return item
    m = _GIVE_NOUN_RX.search(prompt)
    if m:
        candidate = m.group(1).strip().replace(" ", "_").lower()
        if candidate and candidate not in _GIVE_NOUN_DENY:
            return candidate
    return None


def _infer_count_from_prompt(prompt: str) -> int | None:
    m = re.search(r"(\d{1,2})\s*(?:of\s+them|copies|stack|x|\b)", prompt)
    if m:
        try:
            return max(1, min(int(m.group(1)), 64))
        except ValueError:
            return None
    if "a stack of" in prompt or "stack of" in prompt:
        return 64
    return None


def _wants_in_front(prompt: str) -> bool:
    return any(
        kw in prompt
        for kw in (
            "in front of me",
            "in front",
            "ahead of me",
            "ahead",
            "out from me",
            "from here",
            "across the",
            "to the island",
        )
    )


_PARAMETRIC_CONSTRAINT_RX = (
    re.compile(r"\d{1,3}\s*x\s*\d{1,3}", re.I),
    re.compile(r"\bradius\s+\d{1,2}\b", re.I),
    re.compile(r"\d{1,3}\s*blocks?\s*(wide|long|tall|high)\b", re.I),
    re.compile(r"\bexact(ly)?\s+\d{1,3}\b", re.I),
    re.compile(r"\bsize\s+\d{1,2}\b", re.I),
)


def _looks_like_parametric_constraint(prompt: str) -> bool:
    """Explicit dimensions → keep parametric builders, not templates."""

    return any(rx.search(prompt) for rx in _PARAMETRIC_CONSTRAINT_RX)


def _wants_custom_build_params(prompt: str, args: dict[str, Any]) -> bool:
    """Custom block/material in prompt + args → prefer parametric builders."""

    material_hints = (
        "spruce",
        "birch",
        "oak",
        "jungle",
        "dark_oak",
        "fence",
        "planks",
        "slab",
        "wall_block",
        "roof_block",
    )
    if not any(h in prompt for h in material_hints):
        return False
    return any(
        args.get(k)
        for k in ("block", "wall_block", "roof_block", "floor_block", "door_block")
    )


def _infer_template_id_from_prompt(prompt: str, *, intent_family: str = "") -> str | None:
    from agent.templates.ranking import resolve_template
    from agent.routing_context import note_template_ranking

    ranked = resolve_template(prompt, intent_family=intent_family)
    note_template_ranking(ranked)
    if ranked.selected_template_id:
        return ranked.selected_template_id
    return template_catalog.resolve_template_id(prompt.lower())


def _intent_family_for_prompt(prompt: str, template_id: str | None) -> str:
    if _looks_like_bridge_prompt(prompt):
        return "bridge"
    if _looks_like_animal_pen_prompt(prompt):
        return "farm_pen"
    if _looks_like_castle_prompt(prompt):
        return "castle"
    if _looks_like_house_prompt(prompt):
        return "house"
    if _looks_like_give_item_prompt(prompt):
        return "give_item"
    if template_id:
        return "template"
    return "general"


def _note_routing_rewrite(
    original_name: str,
    new_name: str,
    *,
    template_id: str = "",
    fallback_reason: str = "",
    intent_family: str = "",
) -> None:
    rec = current_routing()
    if rec is None:
        return
    if original_name != new_name:
        rec.rewrite_applied = True
        rec.original_tool = original_name
    rec.selected_tool = new_name
    if template_id:
        rec.selected_template_id = template_id
        note_template_provenance(template_id)
    if fallback_reason:
        rec.fallback_reason = fallback_reason
    if intent_family:
        rec.intent_family = intent_family


def _rewrite_to_template(
    req: JobRequest,
    name: str,
    args: dict[str, Any],
    template_id: str,
    intent_family: str,
) -> tuple[str, dict[str, Any]]:
    _note_routing_rewrite(
        name,
        "paste_template_at_player",
        template_id=template_id,
        intent_family=intent_family,
    )
    return "paste_template_at_player", {"player": req.player, "template_id": template_id}


def _normalize_tool_call_for_prompt(
    req: JobRequest, name: str, args: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Deterministic corrections for common language/tool mismatches.

    Returns possibly-rewritten (name, args). Keeps the model's parameter
    intent (length/width/block) wherever possible.
    """

    prompt = (req.prompt or "").lower()
    player = req.player

    intent_family = _intent_family_for_prompt(prompt, None)
    template_id = _infer_template_id_from_prompt(prompt, intent_family=intent_family)
    if not intent_family or intent_family == "general":
        intent_family = _intent_family_for_prompt(prompt, template_id)
    rec = current_routing()
    if rec:
        if intent_family:
            rec.intent_family = intent_family
        if template_id:
            rec.selected_template_id = template_id
            note_template_provenance(template_id)

    # 0a. Shape-word-first: an explicit shape word in the prompt overrides
    # template/parametric routing. "cylinder" wins over castle/fort templates;
    # "sphere" wins over dome templates; "platform" wins over generic floor.
    # Without this rule, "build a hollow stone brick cylinder fort around me"
    # gets fuzzy-matched to a castle template and we lose the cylinder shape.
    if "cylinder" in prompt:
        if name in (
            "build_castle_at_player",
            "build_castle",
            "paste_template_at_player",
            "build_house_at_player",
            "build_house",
            "build_sphere",
            "fawe_sphere_at_player",
            "build_platform",
        ):
            block = args.get("block") or args.get("wall_block") or "stone_bricks"
            radius_raw = args.get("radius") or args.get("size") or 4
            try:
                radius = max(1, int(radius_raw) if not args.get("size") else max(1, int(int(radius_raw) // 2)))
            except (TypeError, ValueError):
                radius = 4
            try:
                height = max(1, int(args.get("height", 8)))
            except (TypeError, ValueError):
                height = 8
            new_args = {
                "player": player,
                "block": str(block),
                "radius": radius,
                "height": height,
                "hollow": bool(args.get("hollow", "hollow" in prompt)),
            }
            return "fawe_cyl_at_player", new_args

    # 0. Template-first: named structures without explicit WxH / radius constraints.
    if (
        template_id
        and not _looks_like_parametric_constraint(prompt)
        and not _wants_custom_build_params(prompt, args)
    ):
        _PARAMETRIC_BUILD_TOOLS = (
            "build_house",
            "build_house_at_player",
            "build_castle_at_player",
            "build_animal_pen_at_player",
            "build_bridge_at_player",
            "build_platform",
            "fill_box",
            "build_cylinder",
            "build_sphere",
            "fawe_as_player",
            "run_command",
        )
        if name in _PARAMETRIC_BUILD_TOOLS:
            return _rewrite_to_template(req, name, args, template_id, intent_family)

    # 1. forward_offset polarity for mine_shaft_at_player
    if name == "mine_shaft_at_player":
        asks_front = any(token in prompt for token in ("front", "frnot", "ahead"))
        asks_behind = "behind" in prompt or "back of me" in prompt
        if asks_front and not asks_behind:
            try:
                current = int(args.get("forward_offset", 1))
            except (TypeError, ValueError):
                current = 1
            args["forward_offset"] = max(1, abs(current))

    # 2. Bridge prompt routed to a digging/fill tool → template or parametric bridge
    if (
        _looks_like_bridge_prompt(prompt)
        and name in ("mine_shaft_at_player", "fill_box", "build_platform")
    ):
        if template_id and not _looks_like_parametric_constraint(prompt):
            return _rewrite_to_template(req, name, args, template_id, "bridge")
        length = None
        width = None
        block = None
        if name == "mine_shaft_at_player":
            length = args.get("depth")
            r = args.get("radius")
            if isinstance(r, int):
                width = max(1, 2 * r + 1)
            elif "forward_offset" in args:
                width = max(1, int(args.get("forward_offset") or 1))
        elif name == "build_platform":
            length = args.get("depth") or args.get("width")
            width = args.get("width") if length == args.get("depth") else args.get("depth")
            block = args.get("block")
        # Pull explicit widths from the prompt if present (e.g. "2 blocks wide")
        m = re.search(r"(\d{1,3})\s*(?:blocks?\s*)?wide", prompt)
        if m:
            width = int(m.group(1))
        m = re.search(r"(\d{1,3})\s*(?:blocks?\s*)?long", prompt)
        if m:
            length = int(m.group(1))
        new_args: dict[str, Any] = {"player": player}
        if length:
            new_args["length"] = max(2, min(int(length), 128))
        if width:
            new_args["width"] = max(1, min(int(width), 8))
        if block:
            new_args["block"] = block
        return "build_bridge_at_player", new_args

    # 3. House / cabin / fort prompts where the model used absolute coords
    if (
        _looks_like_house_prompt(prompt)
        and _wants_in_front(prompt)
        and name in ("build_house", "build_sphere", "fill_box", "build_platform")
        and not (template_id and not _looks_like_parametric_constraint(prompt))
    ):
        new_args = {"player": player}
        for k in ("width", "depth", "height", "wall_block", "roof_block", "door_block", "window_block"):
            if k in args:
                new_args[k] = args[k]
        # Theme inference
        if "sand" in prompt and "wall_block" not in new_args:
            new_args["wall_block"] = "sandstone"
            new_args.setdefault("roof_block", "sandstone_slab")
        if "stone" in prompt and "wall_block" not in new_args:
            new_args["wall_block"] = "stone_bricks"
            new_args.setdefault("roof_block", "stone_brick_slab")
        return "build_house_at_player", new_args

    # 4. Wall in front prompts
    if (
        any(kw in prompt for kw in _WALL_KEYWORDS)
        and name in ("fill_box", "build_platform")
    ):
        return "build_wall_at_player", {"player": player}

    # 5. Castle / fortress / keep prompts that were routed to a solid-fill
    # build tool (build_cylinder, build_sphere, build_platform, fill_box,
    # build_house, build_house_at_player). Castles are NOT cylinders.
    if (
        _looks_like_castle_prompt(prompt)
        and name
        in (
            "build_cylinder",
            "build_sphere",
            "build_platform",
            "fill_box",
            "build_house",
            "build_house_at_player",
        )
        and not (template_id and not _looks_like_parametric_constraint(prompt))
    ):
        new_args: dict[str, Any] = {"player": player}
        # Translate any size hints the model already produced.
        for k_src, k_dst in (
            ("radius", "size"),
            ("width", "size"),
            ("height", "height"),
            ("block", "wall_block"),
            ("wall_block", "wall_block"),
            ("floor_block", "floor_block"),
            ("roof_block", "roof_block"),
        ):
            if k_src in args and args[k_src] is not None:
                new_args[k_dst] = args[k_src]
        if "size" in new_args:
            try:
                # If we converted a radius, double it for the footprint.
                if "radius" in args and "size" not in args and "width" not in args:
                    new_args["size"] = max(7, min(2 * int(args["radius"]) + 1, 31))
                else:
                    new_args["size"] = max(7, min(int(new_args["size"]), 31))
            except (TypeError, ValueError):
                new_args.pop("size", None)
        return "build_castle_at_player", new_args

    # 5b. Animal-pen / coop / hutch prompts misrouted to a generic builder.
    # Anything that produces solid walls or plain floors gets rewritten to
    # build_animal_pen_at_player so the user actually gets a fenced area
    # AND animals. Also patches missing args on correct pen calls (so a
    # "coop" prompt always ends up with with_roof=true).
    if _looks_like_animal_pen_prompt(prompt) and name in (
        "build_house",
        "build_house_at_player",
        "build_platform",
        "fill_box",
        "build_cylinder",
        "build_sphere",
        "build_castle_at_player",
        "summon_entity",
        "build_animal_pen_at_player",
        "paste_template_at_player",
    ):
        if (
            template_id
            and not _looks_like_parametric_constraint(prompt)
            and not _wants_custom_build_params(prompt, args)
        ):
            if name != "paste_template_at_player":
                return _rewrite_to_template(req, name, args, template_id, "farm_pen")
        # When the model already picked the right tool, start from its args
        # and only fill in what's missing or obviously wrong.
        if name == "build_animal_pen_at_player":
            new_args: dict[str, Any] = dict(args)
            new_args.setdefault("player", player)
        else:
            new_args = {"player": player}

        # Animal inference.
        animal_hit = _infer_animal_from_prompt(prompt)
        if "animal" not in new_args or not new_args.get("animal"):
            if animal_hit:
                new_args["animal"] = animal_hit[0]
            elif "coop" in prompt or "hen house" in prompt:
                new_args["animal"] = "chicken"
            elif "hutch" in prompt:
                new_args["animal"] = "rabbit"

        # Roof inference: forced by structure word, else by animal default.
        forced_roof = _wants_pen_roof(prompt)
        if forced_roof:
            new_args["with_roof"] = True
        elif "with_roof" not in new_args:
            if animal_hit and animal_hit[1]:
                new_args["with_roof"] = True

        # Count from prompt overrides the model's count.
        n = _infer_pen_count_from_prompt(prompt)
        if n is not None:
            new_args["count"] = n

        # Preserve block hints if the model produced them via a wrong tool.
        if name != "build_animal_pen_at_player":
            for k_src, k_dst in (
                ("wall_block", "wall_block"),
                ("roof_block", "roof_block"),
                ("floor_block", "floor_block"),
            ):
                if k_src in args and args[k_src] is not None:
                    new_args[k_dst] = args[k_src]
        return "build_animal_pen_at_player", new_args

    # 5c. "Spawn me a <animal>" misrouted to give_item. Send it to
    # summon_entity at the player's current xyz instead.
    if name == "give_item":
        item_arg = (
            str(args.get("item", "")).lower().strip().removeprefix("minecraft:")
        )
        animal_hit = _infer_animal_from_prompt(prompt)
        if animal_hit and (
            item_arg in {animal_hit[0], animal_hit[0] + "s"}
            or item_arg.startswith(animal_hit[0] + "_")
        ):
            entity = animal_hit[0]
            new_args = {
                "entity": entity,
                "x": int(req.x),
                "y": int(req.y),
                "z": int(req.z),
            }
            count = args.get("count")
            if isinstance(count, int) and count >= 1:
                new_args["count"] = min(count, 16)
            return "summon_entity", new_args

    # 6. "Give me a <thing>" prompts that were misrouted to give_haste or to
    # FAWE's nonexistent //give. Translate to a real give_item call.
    if (
        _looks_like_give_item_prompt(prompt)
        and name in ("give_haste", "fawe_as_player", "run_command", "say")
    ):
        item = _infer_item_from_prompt(prompt)
        if item:
            new_args = {"player": player, "item": item}
            count = _infer_count_from_prompt(prompt)
            if count is not None:
                new_args["count"] = count
            return "give_item", new_args

    return name, args


# Back-compat alias for tests that import the old name. Mutates args in
# place when the tool name didn't change; name swaps are exercised via the
# new helper which the orchestrator actually calls.
def _normalize_tool_args_for_prompt(req: JobRequest, name: str, args: dict[str, Any]) -> None:
    new_name, new_args = _normalize_tool_call_for_prompt(req, name, args)
    if new_name == name and new_args is not args:
        args.clear()
        args.update(new_args)


def _build_smart_context(req: JobRequest) -> str:
    """Assemble the upgraded user message: prompt + live world + KB chunks."""
    parts = [build_user_message(req)]
    eval_mode = _is_eval_request(req)
    if not (eval_mode and EVAL_DISABLE_DYNAMIC_CONTEXT):
        try:
            ctx = gather_context(req.player, req.x, req.y, req.z)
            parts.append("")
            parts.append(ctx.render())
        except Exception:
            pass
    if not (eval_mode and EVAL_DISABLE_RETRIEVAL):
        kb = render_kb_block(req.prompt)
        if kb:
            parts.append("")
            parts.append(kb)
    return "\n".join(parts)


async def _run_agent_loop(job: Job) -> None:
    req = job.request
    eval_mode = _is_eval_request(req)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_smart_context(req)},
    ]
    model_used = ""
    failure_streak: dict[str, int] = {}
    LOOP_BREAK_AT = 2
    async with httpx.AsyncClient() as client:
        for step in range(MAX_AGENT_STEPS):
            job.steps = step + 1
            data: dict[str, Any] | None = None
            last_err: Exception | None = None

            if eval_mode:
                # Per-request override > process env > default model
                req_model = (req.eval_model or "").strip()
                candidate_models = [req_model or EVAL_MODEL or OLLAMA_MODEL]
            else:
                candidate_models = [OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL]

            # Local-first, but never let a slow local model freeze in-game chat.
            for candidate in candidate_models:
                if data is not None or not candidate:
                    continue
                try:
                    data = await _chat_completion(
                        client,
                        OLLAMA_BASE,
                        candidate,
                        messages,
                        timeout=EVAL_LOCAL_MODEL_TIMEOUT if eval_mode else LOCAL_MODEL_TIMEOUT,
                        eval_mode=eval_mode,
                    )
                    model_used = f"ollama:{candidate}"
                except Exception as e:
                    last_err = e

            # Cloud fallback
            if (not eval_mode) and data is None and OPENAI_API_KEY:
                try:
                    data = await _chat_completion(
                        client,
                        CLOUD_BASE,
                        CLOUD_MODEL,
                        messages,
                        api_key=OPENAI_API_KEY,
                        eval_mode=eval_mode,
                    )
                    model_used = f"cloud:{CLOUD_MODEL}"
                except Exception as e:
                    last_err = e

            if data is None:
                if job.tool_calls:
                    job.status = JobStatus.done
                    tools = ", ".join(call["name"] for call in job.tool_calls[-3:])
                    job.message = f"Applied {tools}; model was unavailable for final summary."
                    job.model = model_used
                    return
                job.status = JobStatus.failed
                job.message = f"No model available: {last_err}"
                job.model = model_used
                return

            job.model = model_used
            choice = data["choices"][0]
            tool_calls = _parse_tool_calls(choice)
            assistant_msg = choice.get("message", {})
            messages.append(assistant_msg)

            if not tool_calls:
                job.status = JobStatus.done
                job.message = (assistant_msg.get("content") or "Done.").strip()
                return

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]
                player_tools = {
                    "fawe_as_player",
                    "fawe_sphere_at_player",
                    "fawe_cyl_at_player",
                    "mine_shaft_at_player",
                    "get_player_position",
                    "get_player_dimension",
                    "give_haste",
                    "teleport_player",
                    "set_gamemode",
                }
                if name in player_tools and "player" not in args:
                    args["player"] = req.player
                if name in ("paste_template_at_player", "create_template_from_selection"):
                    if "player" not in args:
                        args["player"] = req.player
                original_name = name
                name, args = _normalize_tool_call_for_prompt(req, name, args)
                rec = current_routing()
                if rec and rec.selected_tool == "":
                    rec.selected_tool = name
                if rec and original_name != name and not rec.original_tool:
                    rec.original_tool = original_name
                    rec.rewrite_applied = True

                if requires_confirmation(name, args):
                    token = req.confirm_token
                    if not token or not consume_confirm_token(
                        token=token,
                        player=req.player,
                        prompt=req.prompt,
                        tool=name,
                        arguments=args,
                    ):
                        new_tok = new_confirm_token()
                        issue_confirm_token(
                            player=req.player,
                            prompt=req.prompt,
                            tool=name,
                            arguments=args,
                            token=new_tok,
                        )
                        job.status = JobStatus.done
                        job.message = (
                            f"Destructive action blocked. Confirm with: "
                            f"/agent confirm {new_tok} {req.prompt}"
                        )
                        return

                import asyncio

                result = await asyncio.to_thread(
                    T.execute_tool, name, args, dry_run=req.dry_run
                )
                job.tool_calls.append(
                    {"name": name, "arguments": args, "result": result.to_dict()}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", name),
                        "content": json.dumps(result.to_dict()),
                    }
                )

                signature = f"{name}:{json.dumps(args, sort_keys=True)}"
                if not result.ok:
                    failure_streak[signature] = failure_streak.get(signature, 0) + 1
                    if failure_streak[signature] >= LOOP_BREAK_AT:
                        job.status = JobStatus.failed
                        job.message = (
                            f"Aborting: {name} failed {failure_streak[signature]}x with the same "
                            f"arguments. Last error: {result.error or result.output}"
                        )
                        return
                else:
                    failure_streak[signature] = 0

        job.status = JobStatus.done
        job.message = "Reached max agent steps; partial work may have been applied."


async def _process_job(job_id: str) -> None:
    import logging
    import time

    from agent.metrics import inc, observe

    log = logging.getLogger("neighborhood.agent.job")
    job = _jobs.get(job_id)
    if job is None:
        return
    job.status = JobStatus.running
    start_job(job_id)
    set_current_job(job_id)
    routing_meta: dict[str, Any] = {}
    t0 = time.monotonic()
    log.info(
        "job_start",
        extra={
            "job_id": job_id,
            "player": job.request.player,
            "dry_run": job.request.dry_run,
        },
    )
    try:
        await _run_agent_loop(job)
    except Exception as e:
        job.status = JobStatus.failed
        job.message = str(e)
        inc("jobs_total", labels={"status": "failed"})
    else:
        inc("jobs_total", labels={"status": job.status.value})
    finally:
        observe("job_latency_seconds", time.monotonic() - t0)
        rec = finish_job(job_id)
        set_current_job(None)
        if rec:
            routing_meta = rec.to_dict()
    append_audit(
        AuditEntry(
            job_id=job.id,
            timestamp=utc_now_iso(),
            player=job.request.player,
            uuid=job.request.uuid,
            prompt=job.request.prompt,
            status=job.status.value,
            model=job.model,
            steps=job.steps,
            tool_calls=job.tool_calls,
            message=job.message,
            dry_run=job.request.dry_run,
            routing=routing_meta,
        )
    )
    # Remember the last action per player so a follow-up "/agent good" or
    # "/agent bad <why>" rates THIS job. Only ratable jobs (those that ran
    # tools and weren't themselves feedback) count.
    if job.tool_calls:
        remember_last_job(job.request.player, job.id)
        # Append the feedback hint exactly once per successful, tool-running
        # job — and only when the orchestrator is in chat mode (not eval).
        if (
            ASK_FEEDBACK
            and job.status == JobStatus.done
            and not _is_eval_request(job.request)
            and FEEDBACK_HINT not in job.message
        ):
            job.message = (job.message or "Done.") + FEEDBACK_HINT


@app.get("/health")
async def health() -> dict[str, Any]:
    from agent.tool_registry import TOOLS_SCHEMA_VERSION, TOOLS_VERSION
    from agent.templates import catalog as _tc

    import asyncio

    deps: dict[str, Any] = {}
    try:
        await asyncio.to_thread(T.preflight)
        deps["rcon"] = "ok"
    except Exception as exc:
        deps["rcon"] = f"error: {exc}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags")
            deps["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as exc:
        deps["ollama"] = f"error: {exc}"
    audit_path = audit_log_path()
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8"):
            pass
        deps["audit_writable"] = "ok"
    except Exception as exc:
        deps["audit_writable"] = f"error: {exc}"
    deps["template_count"] = len(list(_tc.iter_templates()))
    overall = (
        "ok"
        if deps.get("rcon") == "ok" and deps.get("audit_writable") == "ok"
        else "degraded"
    )
    return {
        "status": overall,
        "tools_version": TOOLS_VERSION,
        "tools_schema_version": str(TOOLS_SCHEMA_VERSION),
        "dependencies": deps,
    }


@app.get("/metrics")
async def metrics() -> Any:
    from fastapi.responses import PlainTextResponse

    from agent.metrics import prometheus_text

    return PlainTextResponse(prometheus_text(), media_type="text/plain; version=0.0.4")


@app.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """MCP Core v1 capability discovery + tool inventory + template count."""

    from agent.executor import server_capabilities
    from agent.tool_registry import TOOL_DEFINITIONS
    from agent.templates import catalog as _tc

    families: dict[str, list[str]] = {}
    for defn in TOOL_DEFINITIONS:
        families.setdefault(defn.category, []).append(defn.name)
    return {
        "capabilities": server_capabilities(),
        "tool_families": {k: sorted(v) for k, v in families.items()},
        "tool_count": len(TOOL_DEFINITIONS),
        "template_count": len(list(_tc.iter_templates())),
    }


@app.post("/v1/jobs", response_model=JobResponse, dependencies=[Depends(_auth)])
async def create_job(req: JobRequest) -> JobResponse:
    # Detect "/agent good", "/agent bad <why>" etc BEFORE applying the
    # cooldown so quick "good job" follow-ups don't get throttled and BEFORE
    # the LLM ever sees the prompt.
    parsed = parse_rating_prompt(req.prompt or "")
    if parsed is not None:
        return _handle_rating_job(req, parsed)

    # /agent confirm <token> <prompt> — parse before cooldown
    prompt = req.prompt.strip()
    if prompt.lower().startswith("confirm "):
        parts = prompt.split(maxsplit=2)
        if len(parts) >= 3:
            req.confirm_token = parts[1]
            req.prompt = parts[2]

    if not _is_eval_request(req):
        cooldown_msg = check_cooldown(req.uuid)
        if cooldown_msg:
            raise HTTPException(429, cooldown_msg)

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, request=req)
    _jobs.set(job_id, job)

    await _process_job(job_id)

    return JobResponse(
        job_id=job_id,
        status=job.status,
        message=job.message,
        steps=job.steps,
        model=job.model,
        tool_calls=job.tool_calls,
    )


def _handle_rating_job(req: JobRequest, parsed: ParsedRating) -> JobResponse:
    """Persist a rating in lieu of running the agent loop."""

    job_id = str(uuid.uuid4())
    try:
        entry = record_feedback(
            player=req.player,
            rating=parsed.rating,
            note=parsed.note,
            source="chat",
        )
    except LookupError:
        return JobResponse(
            job_id=job_id,
            status=JobStatus.done,
            message=(
                "Nothing to rate yet — run an /agent command first, then "
                "reply with 'good' or 'bad <reason>'."
            ),
            steps=0,
            model="",
            tool_calls=[],
        )

    if parsed.rating == "good":
        msg = "Thanks! Logged 'good' for that one."
    else:
        msg = "Logged 'bad' — we'll use it to tune the agent."
        if parsed.note:
            # Trim long notes for the in-game reply.
            short = (parsed.note[:60] + "…") if len(parsed.note) > 60 else parsed.note
            msg = f"Logged 'bad' ({short}) — we'll use it to tune the agent."

    append_audit(
        AuditEntry(
            job_id=job_id,
            timestamp=utc_now_iso(),
            player=req.player,
            uuid=req.uuid,
            prompt=req.prompt,
            status="feedback",
            model="",
            steps=0,
            tool_calls=[
                {
                    "name": "feedback",
                    "arguments": {
                        "rating": parsed.rating,
                        "note": parsed.note,
                        "for_job_id": entry.job_id,
                    },
                    "result": {"ok": True, "tool": "feedback", "output": entry.feedback_id},
                }
            ],
            message=msg,
            dry_run=False,
        )
    )

    return JobResponse(
        job_id=job_id,
        status=JobStatus.done,
        message=msg,
        steps=0,
        model="",
        tool_calls=[],
    )


class FeedbackRequest(BaseModel):
    rating: str  # "good" | "bad"
    note: str = ""
    player: str | None = None


@app.post(
    "/v1/jobs/{job_id}/feedback",
    response_model=dict[str, Any],
    dependencies=[Depends(_auth)],
)
async def post_feedback(job_id: str, body: FeedbackRequest) -> dict[str, Any]:
    if body.rating not in ("good", "bad"):
        raise HTTPException(400, "rating must be 'good' or 'bad'")
    player = (body.player or "").strip()
    if not player:
        # Resolve player from the audit log so callers without a player can
        # still post feedback for a specific job.
        from agent.feedback import lookup_audit_entry as _lookup_entry

        entry = _lookup_entry(job_id) or {}
        player = entry.get("player", "")
    if not player:
        raise HTTPException(400, "could not determine player for this job")
    try:
        entry = record_feedback(
            player=player,
            rating=body.rating,  # type: ignore[arg-type]
            job_id=job_id,
            note=body.note,
            source="api",
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    return {
        "ok": True,
        "feedback_id": entry.feedback_id,
        "job_id": entry.job_id,
        "rating": entry.rating,
    }


@app.get("/v1/feedback", dependencies=[Depends(_auth)])
async def list_feedback(limit: int = 100, player: str | None = None) -> dict[str, Any]:
    from agent.feedback import iter_feedback

    rows = list(iter_feedback())
    if player:
        needle = player.lower()
        rows = [r for r in rows if (r.get("player") or "").lower() == needle]
    if limit > 0:
        rows = rows[-limit:]
    return {"count": len(rows), "items": rows}


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(_auth)])
async def get_job(job_id: str) -> JobResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobResponse(
        job_id=job_id,
        status=job.status,
        message=job.message,
        steps=job.steps,
        model=job.model,
        tool_calls=job.tool_calls,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "agent.orchestrator:app",
        host=BIND_HOST,
        port=BIND_PORT,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":
    main()
