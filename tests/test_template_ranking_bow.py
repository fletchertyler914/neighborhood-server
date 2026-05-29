"""Hybrid ranker tests with the default bag-of-words embedding backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TEMPLATE_EMBEDDING_BACKEND", "local")
os.environ.setdefault("TEMPLATE_RANKER_MODE", "hybrid")

from agent.templates.ranking import resolve_template  # noqa: E402


def test_chicken_coop_semantic_query():
    result = resolve_template("a place for chickens to live")
    assert result.selected_template_id in (
        "chicken_coop_small",
        "chicken_coop_large",
        "barn_red_large",
        None,
    )
    assert result.confidence in ("high", "medium", "low")
