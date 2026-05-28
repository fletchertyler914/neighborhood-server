"""Lightweight in-process metrics for orchestrator observability."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_histograms: dict[str, list[float]] = defaultdict(list)


def inc(name: str, *, labels: dict[str, str] | None = None, value: int = 1) -> None:
    key = _key(name, labels)
    with _lock:
        _counters[key] += value


def observe(name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
    key = _key(name, labels)
    with _lock:
        _histograms[key].append(value)


def _key(name: str, labels: dict[str, str] | None) -> str:
    if not labels:
        return name
    parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "counters": dict(_counters),
            "histograms": {k: list(v) for k, v in _histograms.items()},
        }


def prometheus_text() -> str:
    lines: list[str] = []
    with _lock:
        for key, val in sorted(_counters.items()):
            metric, _, label_str = key.partition("{")
            if label_str:
                lines.append(f"{metric}{{{label_str} {val}")
            else:
                lines.append(f"{metric} {val}")
        for key, vals in sorted(_histograms.items()):
            if not vals:
                continue
            metric, _, label_str = key.partition("{")
            suffix = f"{{{label_str}" if label_str else ""
            lines.append(f"{metric}_count{suffix} {len(vals)}")
            lines.append(f"{metric}_sum{suffix} {sum(vals)}")
    return "\n".join(lines) + "\n"
