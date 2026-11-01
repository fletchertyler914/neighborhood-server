"""Idempotent candidate dedup (source id + content hash)."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_url TEXT,
  title TEXT,
  author TEXT,
  license TEXT,
  intent_id TEXT,
  match_score REAL,
  match_reason TEXT,
  block_count INTEGER,
  size_x INTEGER,
  size_y INTEGER,
  size_z INTEGER,
  download_path TEXT,
  schem_path TEXT,
  content_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'seen',
  promoted_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS content_hashes (
  sha256 TEXT PRIMARY KEY,
  first_source TEXT,
  first_source_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def seen_source(con: sqlite3.Connection, source: str, source_id: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM candidates WHERE source=? AND source_id=?",
        (source, source_id),
    ).fetchone()
    return row is not None


def content_seen(con: sqlite3.Connection, sha256: str) -> bool:
    row = con.execute("SELECT 1 FROM content_hashes WHERE sha256=?", (sha256,)).fetchone()
    return row is not None


def upsert_candidate(con: sqlite3.Connection, row: dict) -> int:
    con.execute(
        """
        INSERT INTO candidates (
          source, source_id, source_url, title, author, license,
          intent_id, match_score, match_reason, block_count,
          size_x, size_y, size_z, download_path, schem_path,
          content_sha256, status, promoted_id, error
        ) VALUES (
          :source, :source_id, :source_url, :title, :author, :license,
          :intent_id, :match_score, :match_reason, :block_count,
          :size_x, :size_y, :size_z, :download_path, :schem_path,
          :content_sha256, :status, :promoted_id, :error
        )
        ON CONFLICT(source, source_id) DO UPDATE SET
          source_url=excluded.source_url,
          title=excluded.title,
          author=excluded.author,
          license=excluded.license,
          intent_id=excluded.intent_id,
          match_score=excluded.match_score,
          match_reason=excluded.match_reason,
          block_count=excluded.block_count,
          size_x=excluded.size_x,
          size_y=excluded.size_y,
          size_z=excluded.size_z,
          download_path=COALESCE(excluded.download_path, candidates.download_path),
          schem_path=COALESCE(excluded.schem_path, candidates.schem_path),
          content_sha256=COALESCE(excluded.content_sha256, candidates.content_sha256),
          status=excluded.status,
          promoted_id=COALESCE(excluded.promoted_id, candidates.promoted_id),
          error=excluded.error,
          updated_at=datetime('now')
        """,
        row,
    )
    con.commit()
    cur = con.execute(
        "SELECT id FROM candidates WHERE source=? AND source_id=?",
        (row["source"], row["source_id"]),
    )
    return int(cur.fetchone()["id"])


def record_content_hash(
    con: sqlite3.Connection, sha256: str, source: str, source_id: str
) -> None:
    con.execute(
        """
        INSERT OR IGNORE INTO content_hashes (sha256, first_source, first_source_id)
        VALUES (?, ?, ?)
        """,
        (sha256, source, source_id),
    )
    con.commit()
