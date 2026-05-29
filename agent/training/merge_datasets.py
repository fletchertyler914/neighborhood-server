"""Merge corpus + feedback exports into one training set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


def _fingerprint(row: dict[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_deduped(rows: list[dict[str, Any]], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            fp = _fingerprint(row)
            if fp in seen:
                continue
            seen.add(fp)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def merge_training_datasets(
    *,
    sft_inputs: list[Path],
    dpo_inputs: list[Path],
    sft_out: Path,
    dpo_out: Path,
) -> dict[str, int]:
    """Merge and de-duplicate SFT and DPO JSONL files."""

    sft_rows: list[dict[str, Any]] = []
    dpo_rows: list[dict[str, Any]] = []
    for path in sft_inputs:
        sft_rows.extend(_iter_jsonl(path))
    for path in dpo_inputs:
        dpo_rows.extend(_iter_jsonl(path))
    return {
        "sft_inputs": len(sft_rows),
        "dpo_inputs": len(dpo_rows),
        "sft": _write_deduped(sft_rows, sft_out),
        "dpo": _write_deduped(dpo_rows, dpo_out),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Merge corpus + feedback datasets")
    parser.add_argument("--sft", type=Path, action="append", default=[])
    parser.add_argument("--dpo", type=Path, action="append", default=[])
    parser.add_argument("--sft-out", type=Path, default=Path("datasets/sft/train.jsonl"))
    parser.add_argument("--dpo-out", type=Path, default=Path("datasets/preferences/train.jsonl"))
    args = parser.parse_args()
    stats = merge_training_datasets(
        sft_inputs=args.sft,
        dpo_inputs=args.dpo,
        sft_out=args.sft_out,
        dpo_out=args.dpo_out,
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
