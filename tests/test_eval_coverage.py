from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.coverage import load_coverage, required_case_ids, validate_coverage
from agent.eval.loader import load_cases


def test_coverage_required_cases_exist():
    suite = load_cases(ROOT / "agent" / "eval" / "cases")
    coverage = load_coverage(ROOT / "agent" / "eval" / "coverage.yaml")
    required = required_case_ids(coverage)
    present = {c.id for c in suite.cases}
    assert required.issubset(present)


def test_validate_coverage_passes_for_current_suite():
    suite = load_cases(ROOT / "agent" / "eval" / "cases")
    errors = validate_coverage(suite.cases, ROOT / "agent" / "eval" / "coverage.yaml")
    assert errors == []
