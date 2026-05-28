"""Convert player feedback into supervised + preference training data.

Feedback flow:
1. Player runs ``/agent build a castle`` → orchestrator runs tools, writes
   audit entry with ``job_id``.
2. Player runs ``/agent good`` or ``/agent bad <why>`` → orchestrator
   writes a feedback record (see :mod:`agent.feedback`).
3. This module joins ``data/agent-feedback.jsonl`` with the audit log to
   produce OpenAI-style SFT pairs from ``good`` jobs and DPO-style
   preference pairs when a prompt has both ``good`` and ``bad`` examples.

The output formats are deliberately framework-agnostic JSONL:

* SFT  : ``{"messages": [{role, content, tool_calls?}, ...], "meta": {...}}``
* DPO  : ``{"prompt": "...", "chosen": [...], "rejected": [...]}``

Downstream trainers (OpenAI fine-tune, axolotl, trl) can consume either
format directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from agent.feedback import feedback_log_path, iter_feedback
from agent.safety import audit_log_path


@dataclass(frozen=True)
class JoinedRow:
    feedback: dict[str, Any]
    audit: dict[str, Any]

    @property
    def rating(self) -> str:
        return str(self.feedback.get("rating") or "")

    @property
    def prompt(self) -> str:
        return str(self.audit.get("prompt") or self.feedback.get("prompt") or "")

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return list(self.audit.get("tool_calls") or [])


def _index_audit_by_job(audit_path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not audit_path.exists():
        return out
    with audit_path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            job_id = obj.get("job_id") or obj.get("uuid")
            if not job_id:
                continue
            # Last write wins (re-runs of the same job_id).
            if obj.get("status") == "feedback":
                continue
            out[job_id] = obj
    return out


def join_feedback(
    feedback_path: Path | None = None,
    audit_path: Path | None = None,
) -> Iterator[JoinedRow]:
    """Yield (feedback, audit) pairs for each rated job we can resolve."""

    fb_path = feedback_path or feedback_log_path()
    a_path = audit_path or audit_log_path()
    audit_index = _index_audit_by_job(a_path)
    if not fb_path.exists():
        return
    for fb in iter_feedback() if feedback_path is None else _iter_jsonl(fb_path):
        job_id = fb.get("job_id")
        if not job_id:
            continue
        audit = audit_index.get(job_id)
        if not audit:
            continue
        tool_calls = audit.get("tool_calls") or []
        rating = str(fb.get("rating") or "")
        if not tool_calls and rating != "bad":
            continue
        yield JoinedRow(feedback=fb, audit=audit)


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


# --- SFT (supervised fine-tune) output ----------------------------------


def _tool_calls_for_messages(
    tool_calls: list[dict[str, Any]],
    *,
    job_id: str | None = None,
) -> list[dict[str, Any]]:
    """Translate audit-format tool calls to OpenAI tool_calls list."""
    out: list[dict[str, Any]] = []
    for idx, tc in enumerate(tool_calls):
        name = tc.get("name") or ""
        if not name:
            continue
        args = tc.get("arguments") or {}
        call_id = tc.get("id") or tc.get("tool_call_id")
        if not call_id:
            call_id = f"{job_id or 'job'}:tool:{idx}:{name}"
        out.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return out


def _routing_meta(row: JoinedRow) -> dict[str, Any]:
    """Merge routing fields from audit (preferred) and feedback snapshot."""

    audit_r = row.audit.get("routing")
    fb_r = row.feedback.get("routing")
    merged: dict[str, Any] = {}
    if isinstance(fb_r, dict):
        merged.update(fb_r)
    if isinstance(audit_r, dict):
        merged.update(audit_r)
    return merged


def to_sft_example(row: JoinedRow, *, system_prompt: str | None = None) -> dict[str, Any]:
    """Render a single ``good`` job as an OpenAI chat fine-tune example."""

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": row.prompt})
    job_id = str(row.audit.get("job_id") or "")
    tool_calls = _tool_calls_for_messages(row.tool_calls, job_id=job_id)
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": row.audit.get("message") or "",
    }
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    messages.append(assistant_msg)
    for idx, tc in enumerate(row.tool_calls):
        result = tc.get("result")
        if result is None:
            continue
        call_id = tool_calls[idx]["id"] if idx < len(tool_calls) else f"{job_id}:tool:{idx}"
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    routing = _routing_meta(row)
    meta: dict[str, Any] = {
        "job_id": row.audit.get("job_id"),
        "feedback_id": row.feedback.get("feedback_id"),
        "rating": row.rating,
        "model": row.audit.get("model"),
        "player": row.audit.get("player"),
        "note": row.feedback.get("note"),
        "timestamp": row.feedback.get("timestamp"),
    }
    for key in (
        "intent_family",
        "selected_tool",
        "selected_template_id",
        "fallback_reason",
        "rewrite_applied",
        "original_tool",
        "source_id",
        "content_hash",
    ):
        if key in routing and routing[key] not in ("", False, None):
            meta[key] = routing[key]
    return {"messages": messages, "meta": meta}


def build_sft(
    rows: Iterable[JoinedRow],
    *,
    system_prompt: str | None = None,
    include_bad_as_negative: bool = False,
) -> list[dict[str, Any]]:
    """Build SFT examples. ``good`` rows by default; pass
    ``include_bad_as_negative=True`` to also emit ``bad`` rows tagged so
    you can filter them downstream (e.g. for hard-negative mining).
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.rating == "good":
            out.append(to_sft_example(row, system_prompt=system_prompt))
        elif row.rating == "bad" and include_bad_as_negative:
            ex = to_sft_example(row, system_prompt=system_prompt)
            ex["meta"]["negative"] = True
            out.append(ex)
    return out


# --- DPO / preference pairs -------------------------------------------


def build_dpo_pairs(rows: Iterable[JoinedRow]) -> list[dict[str, Any]]:
    """Build prompt-grouped (chosen, rejected) tool-call traces.

    The matching is conservative: same exact prompt text. That keeps the
    pairs honest at the cost of some recall. A future version can fuzzy-
    match prompts when we have more data. Pairs where chosen and rejected
    refer to the same audit job or produce identical tool calls are
    dropped — they teach the trainer nothing.
    """
    def _cluster_key(prompt: str) -> str:
        try:
            from agent.templates.embedding_backend import tokenize

            tokens = sorted(set(tokenize(prompt)))[:16]
            return " ".join(tokens) if tokens else prompt.strip().lower()
        except Exception:
            return prompt.strip().lower()

    grouped: dict[str, dict[str, list[JoinedRow]]] = {}
    for row in rows:
        prompt = row.prompt.strip()
        if not prompt:
            continue
        key = _cluster_key(prompt)
        bucket = grouped.setdefault(key, {"good": [], "bad": []})
        if row.rating in bucket:
            bucket[row.rating].append(row)

    pairs: list[dict[str, Any]] = []
    for _cluster, buckets in grouped.items():
        if not buckets["good"] or not buckets["bad"]:
            continue
        for chosen in buckets["good"]:
            chosen_calls = _tool_calls_for_messages(
                chosen.tool_calls, job_id=str(chosen.audit.get("job_id") or "")
            )
            chosen_sig = json.dumps(chosen_calls, sort_keys=True)
            chosen_job = chosen.audit.get("job_id")
            for rejected in buckets["bad"]:
                if rejected.audit.get("job_id") == chosen_job:
                    continue
                rejected_calls = _tool_calls_for_messages(
                    rejected.tool_calls, job_id=str(rejected.audit.get("job_id") or "")
                )
                if json.dumps(rejected_calls, sort_keys=True) == chosen_sig:
                    continue
                chosen_routing = _routing_meta(chosen)
                rejected_routing = _routing_meta(rejected)
                meta: dict[str, Any] = {
                    "chosen_job_id": chosen_job,
                    "rejected_job_id": rejected.audit.get("job_id"),
                    "chosen_note": chosen.feedback.get("note"),
                    "rejected_note": rejected.feedback.get("note"),
                }
                if chosen_routing.get("selected_template_id"):
                    meta["chosen_template_id"] = chosen_routing["selected_template_id"]
                if rejected_routing.get("selected_template_id"):
                    meta["rejected_template_id"] = rejected_routing[
                        "selected_template_id"
                    ]
                if chosen_routing.get("intent_family"):
                    meta["chosen_intent_family"] = chosen_routing["intent_family"]
                if rejected_routing.get("intent_family"):
                    meta["rejected_intent_family"] = rejected_routing["intent_family"]
                pairs.append(
                    {
                        "prompt": chosen.prompt,
                        "chosen": chosen_calls,
                        "rejected": rejected_calls,
                        "meta": meta,
                    }
                )
                break  # one pair per "good" example
    return pairs


def write_jsonl(rows: Iterable[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n
