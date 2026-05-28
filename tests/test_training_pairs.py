from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.training.pairs import build_pairs_from_reviews, write_pairs_jsonl


def test_build_pairs_from_reviews():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "reviews.jsonl"
        rows = [
            {"prompt": "build platform", "label": "accept", "trace": [{"name": "build_platform"}]},
            {"prompt": "build platform", "label": "reject", "trace": [{"name": "run_command"}]},
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        pairs = build_pairs_from_reviews(path)
        assert len(pairs) == 1
        assert pairs[0].chosen_trace[0]["name"] == "build_platform"
        out = Path(td) / "pairs.jsonl"
        assert write_pairs_jsonl(pairs, out) == 1
