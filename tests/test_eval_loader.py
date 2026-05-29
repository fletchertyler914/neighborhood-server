from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.loader import filter_cases, load_cases


def test_load_smoke_cases():
    suite = load_cases(ROOT / "agent" / "eval" / "cases")

    ids = {c.id for c in suite.cases}
    assert "smoke.preflight.required" in ids
    assert "smoke.no_destructive_without_confirm" in ids


def test_filter_cases_by_mode_and_category():
    suite = load_cases(ROOT / "agent" / "eval" / "cases")

    cases = filter_cases(suite.cases, mode="spec", category="smoke")

    assert len(cases) >= 2
    assert all(c.category == "smoke" for c in cases)

