"""Tool + world assertion helpers for corpus eval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.eval.assertions import normalize_tool_calls, _is_subset
from agent.eval.corpus_case import CorpusCase, CorpusExpect, ToolExpectAny


@dataclass(frozen=True)
class CorpusFailure:
    kind: str
    message: str
    details: dict[str, Any] | None = None


def _match_tool_any(exp: ToolExpectAny, calls: list[dict[str, Any]]) -> bool:
    for tc in calls:
        if tc.get("name") != exp.name:
            continue
        args = tc.get("arguments") or {}
        result = tc.get("result") or {}
        if not exp.arguments_any:
            return True
        for expected in exp.arguments_any:
            if _is_subset(expected, args):
                return True
        if result.get("ok"):
            return True
    return False


def _semantic_tool_match(expect: CorpusExpect, calls: list[dict[str, Any]]) -> bool:
    """Accept a successful call to any expected tool name (NL synonym tolerance)."""

    expected_names = {exp.name for exp in expect.tool_any}
    for tc in calls:
        if tc.get("name") not in expected_names:
            continue
        if (tc.get("result") or {}).get("ok"):
            return True
    return False


def assert_corpus_expect(
    expect: CorpusExpect,
    *,
    actual_status: str,
    actual_steps: int,
    tool_calls: list[dict[str, Any]],
    world_probe_ok: bool,
    world_probe_message: str,
) -> list[CorpusFailure]:
    failures: list[CorpusFailure] = []
    norm = normalize_tool_calls(tool_calls)

    if expect.status and actual_status != expect.status:
        failures.append(
            CorpusFailure(
                kind="status",
                message=f"expected status={expect.status} got {actual_status}",
            )
        )

    if expect.max_steps is not None and actual_steps > expect.max_steps:
        failures.append(
            CorpusFailure(
                kind="max_steps",
                message=f"expected steps <= {expect.max_steps} got {actual_steps}",
            )
        )

    for forbidden in expect.forbidden_tools:
        if any(tc["name"] == forbidden for tc in norm):
            failures.append(
                CorpusFailure(
                    kind="forbidden_tool",
                    message=f"forbidden tool called: {forbidden}",
                )
            )

    if expect.tool_any:
        matched = any(_match_tool_any(exp, norm) for exp in expect.tool_any)
        if not matched:
            matched = _semantic_tool_match(expect, norm)
        if not matched:
            failures.append(
                CorpusFailure(
                    kind="tool_selection_miss",
                    message=(
                        "expected one of: "
                        + ", ".join(
                            f"{e.name}({e.arguments_any})" for e in expect.tool_any
                        )
                    ),
                    details={"expected": [e.model_dump() for e in expect.tool_any]},
                )
            )

    if not norm and expect.tool_any:
        failures.append(
            CorpusFailure(
                kind="no_tool_calls",
                message="model returned no tool calls",
            )
        )

    for tc in norm:
        result = tc.get("result") or {}
        if isinstance(result, dict) and not result.get("ok", True):
            err = str(result.get("error") or result.get("output") or "")
            kind = "server_error"
            if "unknown template_id" in err.lower():
                kind = "template_unresolved"
            if not any(f.kind in (kind, "tool_selection_miss") for f in failures):
                failures.append(
                    CorpusFailure(
                        kind=kind,
                        message=err[:200] or f"tool {tc['name']} failed",
                    )
                )
            break

    if expect.world_probe and expect.world_probe.kind != "none":
        if not world_probe_ok:
            failures.append(
                CorpusFailure(
                    kind="world_state_wrong",
                    message=world_probe_message,
                )
            )

    return failures


def classify_primary_failure(failures: list[CorpusFailure]) -> str:
    if not failures:
        return "pass"
    priority = [
        "no_tool_calls",
        "tool_selection_miss",
        "template_unresolved",
        "server_error",
        "world_state_wrong",
        "forbidden_tool",
        "status",
        "max_steps",
    ]
    kinds = {f.kind for f in failures}
    for kind in priority:
        if kind in kinds:
            return kind
    return failures[0].kind
