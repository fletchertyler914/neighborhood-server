#!/usr/bin/env python3
"""Export companion SQLite request_gaps for weekly coverage triage."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def _resolve_db(path: Path) -> Path:
    if path.exists():
        return path
    for alt in (
        Path("data/agent/companion.sqlite3"),
        Path("data/companion/companion.sqlite3"),
    ):
        if alt.exists():
            return alt
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(Path("data/companion.sqlite3")),
        help="Path to companion.sqlite3 (docker cp from mc-agent if needed)",
    )
    parser.add_argument(
        "--out",
        default=str(Path("data/companion-gaps-export.jsonl")),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max rows (0 = all)",
    )
    args = parser.parse_args()
    db_path = _resolve_db(Path(args.db))
    if not db_path.exists():
        print(f"missing db: {args.db}")
        print(
            "Tip: docker cp mc-agent:/var/lib/companion/companion.sqlite3 "
            "data/companion.sqlite3"
        )
        return 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "request_gaps" not in tables:
        print(f"no request_gaps table yet in {db_path} (deploy mc-agent first)")
        return 1
    sql = """
        SELECT id, created_ms, player_uuid, player_name, prompt, route, tier,
               reason, message, candidates_json, job_id
        FROM request_gaps
        ORDER BY created_ms DESC
    """
    if args.limit and args.limit > 0:
        sql += f" LIMIT {int(args.limit)}"
    rows = conn.execute(sql).fetchall()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    by_reason: Counter[str] = Counter()
    prompts: Counter[str] = Counter()
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            reason = str(row["reason"] or "unresolved")
            by_reason[reason] += 1
            prompt = str(row["prompt"] or "").strip()
            if prompt:
                prompts[prompt.lower()] += 1
            try:
                candidates = json.loads(row["candidates_json"] or "[]")
            except json.JSONDecodeError:
                candidates = []
            if not isinstance(candidates, list):
                candidates = []
            payload = {
                "gap_id": row["id"],
                "created_ms": row["created_ms"],
                "player_uuid": row["player_uuid"],
                "player_name": row["player_name"],
                "prompt": prompt,
                "route": row["route"],
                "tier": row["tier"],
                "reason": reason,
                "message": row["message"],
                "candidates": candidates,
                "job_id": row["job_id"],
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} gaps → {out}")
    print("by reason:")
    for key, count in sorted(by_reason.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:4d}  {key}")
    if prompts:
        print("top prompts:")
        for prompt, count in prompts.most_common(15):
            print(f"  {count:4d}  {prompt[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
