#!/usr/bin/env python3
"""Export companion SQLite feedback (+ job snapshots) for harness triage."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(Path("data/companion.sqlite3")),
        help="Path to companion.sqlite3",
    )
    parser.add_argument(
        "--out",
        default=str(Path("data/companion-feedback-export.jsonl")),
    )
    args = parser.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        # Pre-release layouts used separate agent/ or companion/ directories.
        for alt in (
            Path("data/agent/companion.sqlite3"),
            Path("data/companion/companion.sqlite3"),
        ):
            if alt.exists():
                db_path = alt
                break
    if not db_path.exists():
        print(f"missing db: {args.db}")
        return 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT f.id, f.rating, f.note, f.created_ms, f.job_id,
               j.prompt, j.route, j.tier, j.status, j.message,
               s.payload_json AS snapshot_json
        FROM feedback f
        LEFT JOIN jobs j ON j.job_id = f.job_id
        LEFT JOIN job_snapshots s ON s.job_id = f.job_id
        ORDER BY f.created_ms DESC
        """
    ).fetchall()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, int] = {}
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            note = str(row["note"] or "")
            tag = "other"
            for candidate in ("wrong_build", "wrong_place", "wrong_size", "other"):
                if note.lower().startswith(candidate):
                    tag = candidate
                    break
            route = str(row["route"] or "")
            bucket = f"{row['rating']}:{tag}:{route.split('.')[0] if route else 'none'}"
            buckets[bucket] = buckets.get(bucket, 0) + 1
            payload = {
                "feedback_id": row["id"],
                "rating": row["rating"],
                "tag": tag,
                "note": note,
                "job_id": row["job_id"],
                "prompt": row["prompt"],
                "route": route,
                "tier": row["tier"],
                "status": row["status"],
                "message": row["message"],
                "snapshot": json.loads(row["snapshot_json"])
                if row["snapshot_json"]
                else None,
                "bucket": bucket,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows → {out}")
    for key, count in sorted(buckets.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:4d}  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
