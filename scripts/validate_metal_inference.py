#!/usr/bin/env python3
"""CLI: validate Metal/MLX inference for one model (exclusive load)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.llm.metal_preflight import unload_all, validate_model  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:11434")
    p.add_argument("--keep-loaded", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    report = validate_model(args.base_url, args.model, unload_first=True)
    if not args.keep_loaded:
        with httpx.Client(timeout=60.0) as client:
            unload_all(client, args.base_url)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"model: {report['model']}")
        print(f"ollama: {report.get('ollama_version')}")
        for c in report["checks"]:
            print(f"  [{'OK' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
        if report.get("residency"):
            r = report["residency"]
            print(
                f"  residency: vram_ratio={r['vram_ratio']} "
                f"format={r.get('format')} ctx={r['context_length']}"
            )
        print(f"RESULT: {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
