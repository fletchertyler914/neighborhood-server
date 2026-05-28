"""Deterministic executor boundary tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.executor import (
    deterministic_signature,
    execute_tool_deterministic,
    server_capabilities,
    validate_tool_arguments,
)
from agent.schema_validate import SchemaValidationError


def test_validate_tool_arguments_applies_defaults():
    args = validate_tool_arguments(
        "build_platform",
        {
            "center_x": 0,
            "y": 80,
            "center_z": 0,
            "width": 5,
            "depth": 5,
            "block": "stone",
        },
    )
    assert args["block"] == "stone"


def test_validate_rejects_unknown_tool():
    try:
        validate_tool_arguments("not_a_real_tool", {})
    except SchemaValidationError as e:
        assert "unknown tool" in str(e)
    else:
        raise AssertionError("expected SchemaValidationError")


def test_deterministic_signature_stable():
    sig1 = deterministic_signature("fill_box", {"x1": 0, "block": "stone"}, ["fill 0 0 0 1 1 1 stone"])
    sig2 = deterministic_signature("fill_box", {"x1": 0, "block": "stone"}, ["fill 0 0 0 1 1 1 stone"])
    assert sig1 == sig2
    assert len(sig1) == 64


def test_execute_tool_deterministic_dry_run_has_signature():
    result = execute_tool_deterministic(
        "build_platform",
        {
            "center_x": 1,
            "y": 64,
            "center_z": 2,
            "width": 3,
            "depth": 3,
            "block": "quartz_block",
        },
        dry_run=True,
    )
    assert result.ok
    assert result.deterministic_signature
    assert result.execution_metadata.get("policy_path") == "typed"


def test_server_capabilities_exposes_versions():
    caps = server_capabilities()
    assert caps["mcp_core_version"] == "1.0.0"
    assert caps["tools_version"] == "2.8.0"
