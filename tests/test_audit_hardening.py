"""Tests for tier-0/1 audit and version hardening."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import mcp_core
from agent.eval.coverage import load_coverage, required_case_ids, validate_coverage
from agent.eval.loader import load_cases
from agent.schema_validate import SchemaValidationError, validate_against_schema
from agent.templates import catalog as template_catalog
from agent.tool_registry import TOOLS_VERSION
from agent.safety import AuditEntry


def test_mcp_tools_version_matches_registry():
    assert mcp_core.TOOLS_VERSION_EXPECTED == TOOLS_VERSION


def test_audit_entry_serializes_world_verification():
    entry = AuditEntry(
        timestamp="t",
        player="Steve",
        uuid="u",
        prompt="build",
        status="done",
        model="m",
        steps=1,
        world_verification={"verified_ok": True, "changed_blocks": 10},
    )

    import json

    payload = json.loads(entry.to_json())
    assert payload["world_verification"]["verified_ok"] is True


def test_say_max_length_enforced():
    schema = {
        "type": "object",
        "properties": {"message": {"type": "string", "minLength": 1, "maxLength": 256}},
        "required": ["message"],
        "additionalProperties": False,
    }
    try:
        validate_against_schema({"message": "x" * 300}, schema)
    except SchemaValidationError as exc:
        assert "too long" in str(exc)
    else:
        raise AssertionError("expected SchemaValidationError")


def test_strict_baseline_covers_ninety_percent_of_spec_cases():
    import json

    suite = load_cases(ROOT / "agent" / "eval" / "cases")
    spec_ids = [c.id for c in suite.cases if any(m.value == "spec" for m in c.modes)]
    baseline = json.loads((ROOT / "agent/eval/baseline.strict.json").read_text())
    covered = set((baseline.get("cases") or {}).keys())
    ratio = len(covered & set(spec_ids)) / max(len(spec_ids), 1)
    assert ratio >= 0.9, f"baseline covers {ratio:.0%} of {len(spec_ids)} spec cases"


def test_catalog_alias_collisions_are_tracked():
    template_catalog.reload_catalog()
    collisions = template_catalog.alias_collisions()
    assert isinstance(collisions, list)
