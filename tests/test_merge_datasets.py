from __future__ import annotations

import json
from pathlib import Path

from agent.training.merge_datasets import merge_training_datasets


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_merge_training_datasets_dedupes_exact_rows(tmp_path: Path):
    sft_a = tmp_path / "sft_a.jsonl"
    sft_b = tmp_path / "sft_b.jsonl"
    dpo_a = tmp_path / "dpo_a.jsonl"
    duplicate = {"messages": [{"role": "user", "content": "build a cabin"}], "meta": {"id": 1}}
    unique = {"messages": [{"role": "user", "content": "build a bridge"}], "meta": {"id": 2}}
    pair = {"prompt": "build a cabin", "chosen": [], "rejected": [], "meta": {"id": 3}}
    _write_jsonl(sft_a, [duplicate])
    _write_jsonl(sft_b, [duplicate, unique])
    _write_jsonl(dpo_a, [pair, pair])

    sft_out = tmp_path / "out" / "train_sft.jsonl"
    dpo_out = tmp_path / "out" / "train_dpo.jsonl"
    stats = merge_training_datasets(
        sft_inputs=[sft_a, sft_b],
        dpo_inputs=[dpo_a],
        sft_out=sft_out,
        dpo_out=dpo_out,
    )

    assert stats == {"sft_inputs": 3, "dpo_inputs": 2, "sft": 2, "dpo": 1}
    assert _read_jsonl(sft_out) == [duplicate, unique]
    assert _read_jsonl(dpo_out) == [pair]


def test_merge_training_datasets_tolerates_missing_inputs(tmp_path: Path):
    sft_out = tmp_path / "sft.jsonl"
    dpo_out = tmp_path / "dpo.jsonl"

    stats = merge_training_datasets(
        sft_inputs=[tmp_path / "missing_sft.jsonl"],
        dpo_inputs=[tmp_path / "missing_dpo.jsonl"],
        sft_out=sft_out,
        dpo_out=dpo_out,
    )

    assert stats == {"sft_inputs": 0, "dpo_inputs": 0, "sft": 0, "dpo": 0}
    assert sft_out.read_text(encoding="utf-8") == ""
    assert dpo_out.read_text(encoding="utf-8") == ""
