from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.eval.case import EvalCase


@dataclass(frozen=True)
class LoadedSuite:
    root: Path
    cases: list[EvalCase]


def load_cases(cases_dir: Path) -> LoadedSuite:
    if not cases_dir.exists():
        raise FileNotFoundError(f"cases dir not found: {cases_dir}")
    cases: list[EvalCase] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = data.get("cases")
        if not isinstance(items, list):
            raise ValueError(f"{path}: expected top-level 'cases: [...]'")
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: case must be mapping")
            cases.append(EvalCase.model_validate(raw))
    _ensure_unique_ids(cases)
    return LoadedSuite(root=cases_dir, cases=cases)


def _ensure_unique_ids(cases: list[EvalCase]) -> None:
    seen: dict[str, int] = {}
    for c in cases:
        seen[c.id] = seen.get(c.id, 0) + 1
    dupes = [k for k, v in seen.items() if v > 1]
    if dupes:
        raise ValueError(f"duplicate case ids: {', '.join(sorted(dupes))}")


def filter_cases(
    cases: list[EvalCase],
    *,
    case_id: str | None = None,
    category: str | None = None,
    mode: str | None = None,
) -> list[EvalCase]:
    out = cases
    if case_id:
        out = [c for c in out if c.id == case_id]
    if category:
        out = [c for c in out if c.category == category]
    if mode:
        out = [c for c in out if any(m.value == mode for m in c.modes)]
    return out

