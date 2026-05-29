"""Safe anchor expression resolver for fallback_steps (${ax}, ${ay+2}, ...)."""

from __future__ import annotations

import re
from typing import Any

_EXPR_RX = re.compile(r"^\$\{([a-z_]+)(?:([+-])(\d+))?\}$")


def resolve_anchor_value(value: Any, *, ax: int, ay: int, az: int) -> Any:
    if not isinstance(value, str):
        return value
    m = _EXPR_RX.match(value.strip())
    if not m:
        return value
    base_name, op, delta_s = m.group(1), m.group(2), m.group(3)
    base_map = {"ax": ax, "ay": ay, "az": az}
    if base_name not in base_map:
        raise ValueError(f"unknown anchor variable: {base_name}")
    n = base_map[base_name]
    if op and delta_s:
        d = int(delta_s)
        n = n + d if op == "+" else n - d
    return n


def resolve_step_args(args: dict[str, Any], *, ax: int, ay: int, az: int) -> dict[str, Any]:
    return {k: resolve_anchor_value(v, ax=ax, ay=ay, az=az) for k, v in args.items()}
