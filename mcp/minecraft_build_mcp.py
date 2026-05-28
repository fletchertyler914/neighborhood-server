#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.16.0",
# ]
# ///
"""Thin Cursor MCP adapter over agent.tools — registers tools from tool_registry."""

from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path
from typing import Any, Literal, Optional, Union

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mcp.server.fastmcp import FastMCP

from agent import tools as T
from agent.executor import execute_tool_deterministic
from agent.tool_registry import (
    TOOL_DEFINITIONS,
    TOOL_DEFINITIONS_BY_NAME,
    validate_registry,
)

mcp = FastMCP("neighborhood-minecraft-builder")


def _text(result: T.ToolResult) -> str:
    if not result.ok:
        return result.summary()
    body = result.output or result.summary()
    if result.deterministic_signature:
        body = f"{body}\n[sig={result.deterministic_signature[:12]} {result.execution_metadata.get('policy_path','typed')}]"
    return body


def _register_tool(defn_name: str) -> None:
    defn = TOOL_DEFINITIONS_BY_NAME[defn_name]
    fn = getattr(T, defn.impl)

    sig = inspect.signature(fn)
    params = [p for p in sig.parameters.values() if p.name != "self"]

    # Synthesize a real def with matching signature so FastMCP can introspect
    # annotations (Literal[...], Optional[...], etc.) using the source function's
    # globals. Avoids "name 'Literal' is not defined" under `from __future__
    # import annotations` where annotations are strings.
    src_globals = getattr(fn, "__globals__", {})

    arg_list = []
    for p in params:
        ann = p.annotation
        ann_str = (
            ann
            if isinstance(ann, str)
            else (getattr(ann, "__name__", None) or repr(ann))
        )
        if p.default is inspect.Parameter.empty:
            arg_list.append(f"{p.name}")
        else:
            default_repr = repr(p.default)
            arg_list.append(f"{p.name}={default_repr}")
    arg_signature = ", ".join(arg_list)

    body_lines = [
        f"def {defn.name}({arg_signature}) -> str:",
        f"    args = {{{', '.join(repr(p.name) + ': ' + p.name for p in params)}}}",
        f"    return _invoke({defn.name!r}, args)",
    ]
    src = "\n".join(body_lines)
    handler_globals: dict[str, Any] = dict(src_globals)
    handler_globals["_invoke"] = _invoke
    handler_globals["__name__"] = src_globals.get("__name__", "agent.tools")
    handler_locals: dict[str, Any] = {}
    exec(
        compile(src, f"<mcp_tool:{defn.name}>", "exec"), handler_globals, handler_locals
    )
    handler = handler_locals[defn.name]
    handler.__doc__ = defn.description
    handler.__annotations__ = dict(getattr(fn, "__annotations__", {}))
    handler.__annotations__["return"] = str

    mcp.tool(name=defn.name)(handler)


def _invoke(tool_name: str, args: dict[str, Any]) -> str:
    result = execute_tool_deterministic(tool_name, args, dry_run=False)
    return _text(result)


validate_registry()
for _d in TOOL_DEFINITIONS:
    if _d.mcp:
        _register_tool(_d.name)


if __name__ == "__main__":
    mcp.run()
