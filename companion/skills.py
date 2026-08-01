from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    id: str
    version: str
    description: str
    intents: list[str]
    latency_tier: str
    risk: str
    tools: list[str]
    limits: dict[str, int] = Field(default_factory=dict)


class Skill:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest = SkillManifest.model_validate(
            yaml.safe_load((root / "skill.yaml").read_text())
        )
        self.prompt = (root / "prompt.md").read_text().strip()
        evals: dict[str, Any] = yaml.safe_load((root / "evals.yaml").read_text())
        self.evals = list(evals.get("cases", []))
        if not self.evals:
            raise ValueError(f"skill {self.manifest.id} has no eval cases")


def load_skills(root: str | Path | None = None) -> dict[str, Skill]:
    base = Path(
        root
        or os.environ.get(
            "COMPANION_SKILLS_PATH",
            Path(__file__).resolve().parents[1] / "skills",
        )
    )
    loaded: dict[str, Skill] = {}
    if not base.exists():
        return loaded
    for manifest_path in sorted(base.glob("*/skill.yaml")):
        skill = Skill(manifest_path.parent)
        if skill.manifest.id in loaded:
            raise ValueError(f"duplicate skill id: {skill.manifest.id}")
        loaded[skill.manifest.id] = skill
    return loaded

