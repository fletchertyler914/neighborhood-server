"""Prompt strategy registry for eval and orchestrator experiments."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class PromptStrategy:
    id: str
    description: str
    disable_retrieval: bool = True
    disable_dynamic_context: bool = True
    system_prompt_suffix: str = ""


STRATEGIES: dict[str, PromptStrategy] = {
    "baseline": PromptStrategy(
        id="baseline",
        description="Deterministic eval defaults: no retrieval, no dynamic context.",
        disable_retrieval=True,
        disable_dynamic_context=True,
    ),
    "full_context": PromptStrategy(
        id="full_context",
        description="Live context + retrieval enabled for richer prompts.",
        disable_retrieval=False,
        disable_dynamic_context=False,
    ),
    "retrieval_only": PromptStrategy(
        id="retrieval_only",
        description="KB retrieval on, dynamic world context off.",
        disable_retrieval=False,
        disable_dynamic_context=True,
    ),
}


def resolve_strategy(strategy_id: str | None = None) -> PromptStrategy:
    sid = (strategy_id or os.environ.get("AGENT_PROMPT_STRATEGY") or "baseline").strip()
    if sid not in STRATEGIES:
        raise ValueError(f"unknown strategy: {sid}; choose from {list(STRATEGIES)}")
    return STRATEGIES[sid]


def apply_strategy_env(strategy: PromptStrategy) -> dict[str, str]:
    """Return env overrides to pass into orchestrator/eval containers."""

    return {
        "AGENT_EVAL_DISABLE_RETRIEVAL": "1" if strategy.disable_retrieval else "0",
        "AGENT_EVAL_DISABLE_DYNAMIC_CONTEXT": "1" if strategy.disable_dynamic_context else "0",
        "AGENT_PROMPT_STRATEGY": strategy.id,
    }


@contextmanager
def strategy_env(strategy: PromptStrategy) -> Iterator[PromptStrategy]:
    """Temporarily apply strategy env vars for a single eval/compare run."""

    overrides = apply_strategy_env(strategy)
    saved: dict[str, str | None] = {}
    for key, value in overrides.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield strategy
    finally:
        for key, prior in saved.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior
