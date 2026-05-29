from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.eval.export import export_jsonl, iter_report_rows


def test_iter_report_rows_includes_envelopes():
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "report.json"
        report.write_text(
            json.dumps(
                {
                    "manifest": {"tools_version": "2.0.0"},
                    "strategy_id": "baseline",
                    "envelopes": [
                        {
                            "case_id": "smoke.preflight",
                            "job_id": "j1",
                            "status": "ok",
                            "steps": 1,
                            "trace": [],
                        }
                    ],
                    "results": [
                        {
                            "case_id": "smoke.preflight",
                            "ok": True,
                            "mode": "spec",
                            "status": "ok",
                            "steps": 1,
                            "prompt": "check server",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        rows = list(iter_report_rows(report))
        sources = {r["source"] for r in rows}
        assert "job_envelope" in sources
        assert "eval_report" in sources
        out = Path(td) / "out.jsonl"
        assert export_jsonl(out_path=out, report_paths=[report]) == len(rows)
