from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.assertions import assert_spec
from agent.eval.loader import load_cases


def test_recorded_gate_fixture_satisfies_spec_cases():
    suite = load_cases(ROOT / "agent" / "eval" / "cases")
    cases = {c.id: c for c in suite.cases if c.expect_spec is not None}
    fixture = json.loads(
        (ROOT / "agent" / "eval" / "fixtures" / "gate.spec.json").read_text(
            encoding="utf-8"
        )
    )

    seen: set[str] = set()
    failures: list[str] = []
    for result in fixture["results"]:
        case_id = result["case_id"]
        case = cases.get(case_id)
        if case is None:
            failures.append(f"fixture has unknown spec case: {case_id}")
            continue
        seen.add(case_id)
        assert case.expect_spec is not None
        case_failures = assert_spec(
            expect=case.expect_spec,
            actual_status=result["status"],
            actual_steps=result["steps"],
            tool_calls=result["tool_calls"],
        )
        failures.extend(f"{case_id}: {f.message}" for f in case_failures)

    missing = sorted(set(cases) - seen)
    failures.extend(f"fixture missing spec case: {case_id}" for case_id in missing)

    assert failures == []

