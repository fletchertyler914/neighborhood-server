#!/usr/bin/env python3
"""Print companion feedback bucket summary + weekly triage next steps."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = ("wrong_build", "wrong_place", "wrong_size", "other")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(ROOT / "data" / "companion.sqlite3"),
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "companion-feedback-export.jsonl"),
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Reuse existing JSONL instead of re-exporting",
    )
    args = parser.parse_args()

    out = Path(args.out)
    if not args.skip_export:
        code = subprocess.call(
            [
                sys.executable,
                str(ROOT / "scripts" / "export_companion_feedback.py"),
                "--db",
                args.db,
                "--out",
                str(out),
            ],
            cwd=str(ROOT),
        )
        if code != 0:
            print(
                "Export failed (missing DB is OK for a dry run). "
                "Continuing with any existing export…",
                file=sys.stderr,
            )

    rows: list[dict] = []
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    by_tag = Counter(str(r.get("tag") or "other") for r in rows)
    by_rating = Counter(str(r.get("rating") or "?") for r in rows)
    bad = [r for r in rows if r.get("rating") == "bad"]

    print("=== Companion weekly triage ===")
    print(f"export: {out}  ({len(rows)} rows)")
    print("ratings:", ", ".join(f"{k}={v}" for k, v in sorted(by_rating.items())) or "(empty)")
    print("tags:   ", ", ".join(f"{t}={by_tag.get(t, 0)}" for t in TAGS))
    if not rows:
        print()
        print("No feedback rows yet. Seed from known failure modes:")
        print("  - wrong_build: sized wall at opening → must finish_wall")
        print("  - wrong_place: free-standing place_shape when opening visible")
        print("  - wrong_size: wall NxN ambiguous → clarify long vs square")
        print("  - wrong_build: non-gold named builds (igloo/wizard) → clarify")
        print("Then: make companion-corpus && make companion-gate")
        return 0

    print()
    print("Recent bad feedback (up to 8):")
    for row in bad[:8]:
        prompt = (row.get("prompt") or "")[:60]
        note = (row.get("note") or "")[:80]
        route = row.get("route") or "?"
        print(f"  [{row.get('tag')}] {prompt!r} → {route}  note={note!r}")

    print()
    print("Next steps:")
    print("  1. Bucket each bad row: wrong_build / wrong_place / wrong_size")
    print("  2. Also run: make companion-gaps-export  # real unfulfilled asks")
    print("  3. Add eighty_seed case(s) or gold/alias fix for the cluster")
    print("  4. make companion-corpus && make companion-gate")
    print("  5. Optional live: AGENT_LIVE_PLAYER=firecrab93 make companion-live-core")
    if by_tag.get("wrong_build") or by_tag.get("wrong_place"):
        print("  hint: finish-vs-place / gold paste mismatches often land here")
    if by_tag.get("wrong_size"):
        print("  hint: check wall NxN clarify + place_shape budgets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
