"""Tool schema contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.schema import TOOL_SCHEMAS
from agent.tool_registry import TOOL_DEFINITIONS, build_openai_schemas, mcp_tool_names, validate_registry
from agent.tools import TOOL_DISPATCH


def test_schema_and_dispatch_stay_in_sync():
    schema_names = {entry["function"]["name"] for entry in TOOL_SCHEMAS}
    dispatch_names = set(TOOL_DISPATCH.keys())
    registry_names = {d.name for d in TOOL_DEFINITIONS}
    assert schema_names == dispatch_names == registry_names


def test_all_schemas_are_strict_objects():
    for entry in TOOL_SCHEMAS:
        params = entry["function"]["parameters"]
        assert params["type"] == "object"
        assert params.get("additionalProperties") is False


def test_mcp_exposes_registry_subset():
    mcp_names = set(mcp_tool_names())
    dispatch_names = set(TOOL_DISPATCH.keys())
    assert mcp_names.issubset(dispatch_names)
    assert "count_blocks_in_box" in mcp_names
    assert "palette_in_box" in mcp_names
    assert "verify_structure" in mcp_names
    assert "fawe_cyl_at_player" in mcp_names
    assert "mine_shaft_at_player" in mcp_names
    assert "build_house" in mcp_names
    assert "build_house_at_player" in mcp_names
    assert "build_bridge_at_player" in mcp_names
    assert "build_wall_at_player" in mcp_names


def test_registry_version_present():
    from agent.tool_registry import TOOLS_VERSION

    assert TOOLS_VERSION
    validate_registry()


def test_build_openai_schemas_matches_exported():
    built = build_openai_schemas(orchestrator_only=True)
    assert len(built) == len(TOOL_SCHEMAS)


def test_validate_tool_arguments_coerces_float_coords():
    from agent.executor import validate_tool_arguments

    args = validate_tool_arguments(
        "build_cylinder",
        {
            "center_x": 10144.5,
            "y": -58,
            "center_z": 10000.5,
            "radius": 6,
            "height": 20,
            "block": "stone_bricks",
            "hollow": False,
        },
    )
    assert args["center_x"] == 10144
    assert args["center_z"] == 10000
