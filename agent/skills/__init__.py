"""OSS skill packages — prompt slice + tool allowlist."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.contracts.core import CORE_TOOL_NAMES, core_openai_schemas, get_core_definition

_SKILLS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Skill:
    id: str
    prompt: str
    tools: tuple[str, ...]
    max_steps: int = 1


def _skill_dir(skill_id: str) -> Path:
    return _SKILLS_DIR / skill_id


def list_skills() -> list[str]:
    return sorted(
        p.name
        for p in _SKILLS_DIR.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )


def load_skill(skill_id: str) -> Skill:
    d = _skill_dir(skill_id)
    if not d.is_dir():
        skill_id = "meta"
        d = _skill_dir(skill_id)
    prompt = (d / "SKILL.md").read_text(encoding="utf-8")
    tools_path = d / "tools.json"
    if tools_path.exists():
        tools = tuple(json.loads(tools_path.read_text(encoding="utf-8")))
    else:
        tools = CORE_TOOL_NAMES
    # Only allow core tools
    tools = tuple(t for t in tools if t in CORE_TOOL_NAMES)
    max_steps = 1
    policy = d / "policy.yaml"
    if policy.exists():
        data = yaml.safe_load(policy.read_text(encoding="utf-8")) or {}
        max_steps = int(data.get("max_steps", 1))
    return Skill(id=skill_id, prompt=prompt, tools=tools, max_steps=max_steps)


def schemas_for_skill(skill_id: str) -> list[dict]:
    skill = load_skill(skill_id)
    if not skill.tools:
        return core_openai_schemas()
    return [get_core_definition(n).to_openai_schema() for n in skill.tools]


def select_skill(prompt: str) -> str:
    """Tiny keyword router — KISS until L5 proves we need ML."""

    t = prompt.strip().lower()
    if re.search(
        r"\b(time|weather|rain|sunny|day|night|give\s+me|gamemode|tp\b|teleport)\b",
        t,
    ) and not re.search(r"\b(build|castle|coop|house|sphere|cylinder)\b", t):
        return "admin"
    if re.search(r"\b(summon|spawn|chicken|cow|pig|sheep|horse|mob)\b", t) and not re.search(
        r"\b(coop|pen|stable|build)\b", t
    ):
        return "mobs"
    if re.search(
        r"\b(build|paste|cabin|house|castle|coop|bridge|sphere|cylinder|platform|template|fort)\b",
        t,
    ):
        return "build"
    if re.search(r"\b(help|what can you|status|preflight|list templates)\b", t):
        return "meta"
    return "build"
