from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent.eval.case import SpecExpect, ToolCallExpectation


@dataclass(frozen=True)
class AssertionFailure:
    kind: str
    message: str
    details: dict[str, Any] | None = None


def normalize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        name = tc.get("name") or ""
        args = tc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        out.append({"name": name, "arguments": _sorted(args), "result": tc.get("result")})
    return out


def _sorted(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _sorted(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_sorted(x) for x in v]
    return v


def assert_spec(
    *,
    expect: SpecExpect,
    actual_status: str,
    actual_steps: int,
    tool_calls: list[dict[str, Any]],
) -> list[AssertionFailure]:
    failures: list[AssertionFailure] = []
    norm = normalize_tool_calls(tool_calls)

    if expect.status and actual_status != expect.status:
        failures.append(
            AssertionFailure(
                kind="status",
                message=f"expected status={expect.status} got {actual_status}",
            )
        )

    if expect.max_steps is not None and actual_steps > expect.max_steps:
        failures.append(
            AssertionFailure(
                kind="max_steps",
                message=f"expected steps <= {expect.max_steps} got {actual_steps}",
            )
        )

    for forbidden in expect.forbidden_tools:
        if any(tc["name"] == forbidden for tc in norm):
            failures.append(
                AssertionFailure(
                    kind="forbidden_tool",
                    message=f"forbidden tool called: {forbidden}",
                )
            )

    for exp in expect.must_call:
        if not _match_expected_call(exp, norm):
            failures.append(
                AssertionFailure(
                    kind="must_call",
                    message=f"expected tool call not found: {exp.name}",
                    details={"expected": exp.model_dump()},
                )
            )

    if expect.must_call_in_order:
        names = [tc["name"] for tc in norm]
        if not _is_subsequence(expect.must_call_in_order, names):
            failures.append(
                AssertionFailure(
                    kind="order",
                    message=f"expected tool order subsequence not found: {expect.must_call_in_order}",
                    details={"actual": names},
                )
            )

    return failures


def _match_expected_call(exp: ToolCallExpectation, calls: list[dict[str, Any]]) -> bool:
    for tc in calls:
        if tc["name"] != exp.name:
            continue
        if exp.arguments is None:
            return True
        if _is_subset(exp.arguments, tc.get("arguments") or {}):
            return True
    return False


def _is_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, v in expected.items():
            if k not in actual:
                return False
            if not _is_subset(v, actual[k]):
                return False
        return True
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return False
        return all(_is_subset(e, a) for e, a in zip(expected, actual))
    return expected == actual


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    try:
        for n in needle:
            while True:
                if next(it) == n:
                    break
        return True
    except StopIteration:
        return False

