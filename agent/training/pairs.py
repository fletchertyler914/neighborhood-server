"""Preference pair builder for future DPO / RLHF pipelines."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class PreferencePair:
    prompt: str
    chosen_trace: list[dict[str, Any]]
    rejected_trace: list[dict[str, Any]]
    case_id: str | None = None
    model_chosen: str | None = None
    model_rejected: str | None = None
    review_status: str = "pending"


def iter_review_rows(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def build_pairs_from_reviews(
    reviews_path: Path,
    *,
    accept_label: str = "accept",
    reject_label: str = "reject",
) -> list[PreferencePair]:
    """Build preference pairs from human-labeled review JSONL.

    Expected review row shape (minimal):
      {"prompt": "...", "trace": [...], "label": "accept"|"reject", "case_id": "..."}
    Group by prompt; first accept vs first reject becomes a pair.
    """

    by_prompt: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in iter_review_rows(reviews_path):
        prompt = str(row.get("prompt") or "")
        if not prompt:
            continue
        label = str(row.get("label") or "").lower()
        bucket = by_prompt.setdefault(prompt, {accept_label: [], reject_label: []})
        if label in bucket:
            bucket[label].append(row)

    pairs: list[PreferencePair] = []
    for prompt, buckets in by_prompt.items():
        if not buckets[accept_label] or not buckets[reject_label]:
            continue
        chosen = buckets[accept_label][0]
        rejected = buckets[reject_label][0]
        pairs.append(
            PreferencePair(
                prompt=prompt,
                chosen_trace=chosen.get("trace") or chosen.get("tool_calls") or [],
                rejected_trace=rejected.get("trace") or rejected.get("tool_calls") or [],
                case_id=chosen.get("case_id"),
                model_chosen=chosen.get("model"),
                model_rejected=rejected.get("model"),
                review_status="labeled",
            )
        )
    return pairs


def write_pairs_jsonl(pairs: list[PreferencePair], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(asdict(p), sort_keys=True) + "\n")
    return len(pairs)
