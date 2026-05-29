"""Build SFT + DPO datasets from corpus run envelopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from agent.training.feedback import write_jsonl


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def iter_envelopes(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        for r in data.get("results", []):
            yield r
        return
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _cluster_key(prompt: str) -> str:
    try:
        from agent.templates.embedding_backend import tokenize

        tokens = sorted(set(tokenize(prompt)))[:16]
        return " ".join(tokens) if tokens else prompt.strip().lower()
    except Exception:
        return prompt.strip().lower()


def _tool_signature(trace: list[dict[str, Any]]) -> str:
    return json.dumps(
        [{"name": t.get("name"), "arguments": t.get("arguments")} for t in trace],
        sort_keys=True,
    )


def _trace_to_openai_tool_calls(trace: list[dict[str, Any]], *, job_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, tc in enumerate(trace):
        name = tc.get("name") or ""
        if not name:
            continue
        out.append(
            {
                "id": f"{job_id}:tool:{idx}:{name}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                },
            }
        )
    return out


def build_sft_from_envelopes(
    rows: list[dict[str, Any]],
    *,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("ok"):
            continue
        trace = row.get("trace") or []
        if not trace:
            continue
        key = _cluster_key(str(row.get("prompt") or "")) + "|" + _tool_signature(trace)
        if key in seen:
            continue
        seen.add(key)
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": str(row.get("prompt") or "")})
        job_id = str(row.get("job_id") or row.get("case_id") or "corpus")
        tool_calls = _trace_to_openai_tool_calls(trace, job_id=job_id)
        assistant: dict[str, Any] = {"role": "assistant", "content": ""}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        messages.append(assistant)
        for idx, tc in enumerate(trace):
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
        out.append(
            {
                "messages": messages,
                "meta": {
                    "case_id": row.get("case_id"),
                    "category": row.get("category"),
                    "intent": row.get("intent"),
                    "model": row.get("model"),
                    "temperature": row.get("temperature"),
                },
            }
        )
    return out


def build_dpo_from_envelopes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        prompt = str(row.get("prompt") or "").strip()
        if not prompt:
            continue
        key = _cluster_key(prompt)
        bucket = grouped.setdefault(key, {"pass": [], "fail": []})
        if row.get("ok"):
            bucket["pass"].append(row)
        else:
            bucket["fail"].append(row)

    pairs: list[dict[str, Any]] = []
    for key, buckets in grouped.items():
        if not buckets["pass"] or not buckets["fail"]:
            continue
        chosen = min(buckets["pass"], key=lambda r: (r.get("steps") or 99, r.get("case_id") or ""))
        rejected = max(
            buckets["fail"],
            key=lambda r: (len(r.get("failures") or []), r.get("case_id") or ""),
        )
        chosen_trace = chosen.get("trace") or []
        rejected_trace = rejected.get("trace") or []
        if _tool_signature(chosen_trace) == _tool_signature(rejected_trace):
            continue
        pairs.append(
            {
                "prompt": chosen.get("prompt") or rejected.get("prompt"),
                "chosen": _trace_to_openai_tool_calls(
                    chosen_trace, job_id=str(chosen.get("job_id") or "pass")
                ),
                "rejected": _trace_to_openai_tool_calls(
                    rejected_trace, job_id=str(rejected.get("job_id") or "fail")
                ),
                "meta": {
                    "cluster_key": key,
                    "chosen_case_id": chosen.get("case_id"),
                    "rejected_case_id": rejected.get("case_id"),
                },
            }
        )
    return pairs


def collect_envelope_rows(run_dir: Path) -> list[dict[str, Any]]:
    run_dir = run_dir.resolve()
    rows: list[dict[str, Any]] = []
    main_env = run_dir / "envelopes.jsonl"
    rows.extend(list(iter_envelopes(main_env)))
    resampled = run_dir / "resampled" / "combined.json"
    if resampled.exists():
        rows.extend(list(iter_envelopes(resampled)))
    for sub in (run_dir / "resampled").glob("t*"):
        env = sub / "envelopes.jsonl"
        rows.extend(list(iter_envelopes(env)))
    return rows


def export_corpus_datasets(
    *,
    run_dir: Path,
    sft_out: Path,
    dpo_out: Path,
    system_prompt_path: Path | None = None,
) -> dict[str, int]:
    rows = collect_envelope_rows(run_dir)
    system_prompt = None
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    sft = build_sft_from_envelopes(rows, system_prompt=system_prompt)
    dpo = build_dpo_from_envelopes(rows)
    sft_n = write_jsonl(sft, sft_out)
    dpo_n = write_jsonl(dpo, dpo_out)
    return {"envelopes": len(rows), "sft": sft_n, "dpo": dpo_n}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export corpus run to SFT/DPO JSONL")
    parser.add_argument("--run", type=Path, default=Path("data/corpus-runs/latest"))
    parser.add_argument("--sft-out", type=Path, default=Path("datasets/sft/corpus.jsonl"))
    parser.add_argument("--dpo-out", type=Path, default=Path("datasets/preferences/corpus.jsonl"))
    parser.add_argument("--system-prompt", type=Path, default=Path("agent/prompts/system.md"))
    args = parser.parse_args()
    run_dir = args.run.resolve()
    if run_dir.name == "latest":
        run_dir = run_dir.resolve()
    stats = export_corpus_datasets(
        run_dir=run_dir,
        sft_out=args.sft_out.resolve(),
        dpo_out=args.dpo_out.resolve(),
        system_prompt_path=args.system_prompt_path.resolve(),
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
