"""Deterministic tool executor: schema validation + command signatures."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.mcp_core import MCP_CORE_VERSION, default_capabilities
from agent.schema_validate import (
    SchemaValidationError,
    coerce_to_schema,
    validate_against_schema,
)
from agent.tool_registry import TOOL_DEFINITIONS_BY_NAME, TOOLS_VERSION

# Late import avoids circular dependency at module load.
_tools_module: Any = None


def _tools():
    global _tools_module
    if _tools_module is None:
        from agent import tools as t

        _tools_module = t
    return _tools_module


@dataclass
class ExecutionMetadata:
    policy_path: str = "typed"  # typed | fallback | escape_hatch
    safety_level: str = "low"
    world_namespace: str = "default"
    server_capability_version: str = MCP_CORE_VERSION

    def to_dict(self) -> dict[str, str]:
        return {
            "policy_path": self.policy_path,
            "safety_level": self.safety_level,
            "world_namespace": self.world_namespace,
            "server_capability_version": self.server_capability_version,
        }


def normalize_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Apply schema defaults and strip unknown keys when schema is strict."""

    defn = TOOL_DEFINITIONS_BY_NAME.get(name)
    if defn is None:
        return dict(arguments)
    schema = defn.parameters
    props = schema.get("properties") or {}
    out: dict[str, Any] = {}
    for key, sub in props.items():
        if key in arguments:
            out[key] = arguments[key]
        elif "default" in sub:
            out[key] = sub["default"]
    required = schema.get("required") or []
    for key in required:
        if key not in out and key not in arguments:
            pass  # validation will catch
    if schema.get("additionalProperties") is False:
        extra = set(arguments) - set(out)
        if extra:
            raise SchemaValidationError(f"unknown properties: {sorted(extra)}")
        return out
    for key, val in arguments.items():
        if key not in out:
            out[key] = val
    return out


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    defn = TOOL_DEFINITIONS_BY_NAME.get(name)
    if defn is None:
        raise SchemaValidationError(f"unknown tool: {name}")
    normalized = normalize_arguments(name, arguments)
    coerced = coerce_to_schema(normalized, defn.parameters)
    validate_against_schema(coerced, defn.parameters)
    return coerced


def deterministic_signature(
    tool: str,
    arguments: dict[str, Any],
    commands: list[str] | None = None,
) -> str:
    """SHA-256 of normalized tool call plan (for drift detection)."""

    payload = {
        "tool": tool,
        "arguments": arguments,
        "commands": commands or [],
        "tools_version": TOOLS_VERSION,
        "mcp_core_version": MCP_CORE_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def enrich_result(
    result: Any,
    *,
    metadata: ExecutionMetadata | None = None,
    arguments: dict[str, Any] | None = None,
) -> Any:
    """Attach deterministic_signature and execution_metadata to ToolResult."""

    meta = metadata or ExecutionMetadata()
    sig = deterministic_signature(
        result.tool,
        arguments or {},
        list(result.commands) if result.commands else [],
    )
    result.deterministic_signature = sig
    result.execution_metadata = meta.to_dict()
    return result


def execute_tool_deterministic(
    name: str,
    arguments: dict[str, Any],
    *,
    dry_run: bool = False,
    policy_path: str = "typed",
) -> Any:
    """Validate args, dispatch tool, attach signature + metadata."""

    tools = _tools()
    defn = TOOL_DEFINITIONS_BY_NAME.get(name)
    if defn is None:
        return tools._execute_tool_raw(name, arguments, dry_run=dry_run)
    try:
        normalized = validate_tool_arguments(name, arguments)
    except SchemaValidationError as e:
        return tools._err(name, e)

    if name in ("fawe_as_player", "run_command"):
        policy_path = "escape_hatch"
    meta = ExecutionMetadata(
        policy_path=policy_path,
        safety_level=defn.risk,
    )
    result = tools._execute_tool_raw(name, normalized, dry_run=dry_run)
    if dry_run and result.ok:
        sig = deterministic_signature(name, normalized, [])
        result.deterministic_signature = sig
        result.execution_metadata = meta.to_dict()
        return result
    return enrich_result(result, metadata=meta, arguments=normalized)


def server_capabilities() -> dict[str, str | bool]:
    return default_capabilities(tools_version=TOOLS_VERSION).to_dict()
