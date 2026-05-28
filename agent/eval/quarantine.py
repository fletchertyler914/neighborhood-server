"""Quarantine list for temporarily skipped eval cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.eval.case import EvalCase


@dataclass(frozen=True)
class QuarantineEntry:
    case_id: str
    reason: str = ""
    owner: str = ""


def load_quarantine(path: Path) -> list[QuarantineEntry]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("cases") or []
    out: list[QuarantineEntry] = []
    for item in raw:
        if isinstance(item, str):
            out.append(QuarantineEntry(case_id=item))
        elif isinstance(item, dict) and item.get("id"):
            out.append(
                QuarantineEntry(
                    case_id=str(item["id"]),
                    reason=str(item.get("reason") or ""),
                    owner=str(item.get("owner") or ""),
                )
            )
    return out


def filter_quarantined(cases: list[EvalCase], path: Path) -> list[EvalCase]:
    q = {e.case_id for e in load_quarantine(path)}
    if not q:
        return cases
    return [c for c in cases if c.id not in q]
