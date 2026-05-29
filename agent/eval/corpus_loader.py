"""Load corpus YAML suites from agent/eval/corpus/."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.eval.corpus_case import CorpusCase


@dataclass(frozen=True)
class LoadedCorpus:
    root: Path
    cases: list[CorpusCase]


def default_corpus_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "agent" / "eval" / "corpus"


def load_corpus(corpus_dir: Path | None = None) -> LoadedCorpus:
    directory = corpus_dir or default_corpus_dir()
    if not directory.exists():
        raise FileNotFoundError(f"corpus dir not found: {directory}")
    cases: list[CorpusCase] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = data.get("cases")
        if not isinstance(items, list):
            raise ValueError(f"{path}: expected top-level 'cases: [...]'")
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"{path}: case must be mapping")
            cases.append(CorpusCase.model_validate(raw))
    _ensure_unique_ids(cases)
    return LoadedCorpus(root=directory, cases=cases)


def _ensure_unique_ids(cases: list[CorpusCase]) -> None:
    seen: dict[str, int] = {}
    for c in cases:
        seen[c.id] = seen.get(c.id, 0) + 1
    dupes = [k for k, v in seen.items() if v > 1]
    if dupes:
        raise ValueError(f"duplicate corpus ids: {', '.join(sorted(dupes))}")


def filter_corpus_cases(
    cases: list[CorpusCase],
    *,
    case_id: str | None = None,
    category: str | None = None,
    language_style: str | None = None,
    limit: int | None = None,
) -> list[CorpusCase]:
    out = cases
    if case_id:
        out = [c for c in out if c.id == case_id]
    if category:
        out = [c for c in out if c.category == category]
    if language_style:
        out = [c for c in out if c.language_style == language_style]
    only_path = os.environ.get("AGENT_CORPUS_ONLY_IDS")
    if only_path:
        ids = {
            line.strip()
            for line in Path(only_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        out = [c for c in out if c.id in ids]
    env_limit = os.environ.get("AGENT_CORPUS_LIMIT")
    effective_limit = limit
    if env_limit:
        try:
            effective_limit = int(env_limit) if effective_limit is None else min(
                effective_limit, int(env_limit)
            )
        except ValueError:
            pass
    if effective_limit is not None and effective_limit > 0:
        out = out[:effective_limit]
    return out
