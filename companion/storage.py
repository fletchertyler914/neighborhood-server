from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_IO_RETRIES = 4
_IO_RETRY_SLEEP_SEC = 0.05


class JobStore:
    """Small durable job/action journal using SQLite WAL."""

    def __init__(self, path: str | Path) -> None:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # timeout: wait on locks; busy_timeout: same for SQL level.
        # Named docker volume (not virtiofs bind) avoids macOS disk I/O errors.
        self._db = sqlite3.connect(
            db_path, check_same_thread=False, timeout=30.0
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA temp_store=MEMORY")
        self._db.execute("PRAGMA wal_autocheckpoint=1000")
        self._migrate()

    def _with_retry(self, fn: Callable[[], T]) -> T:
        last: BaseException | None = None
        for attempt in range(_IO_RETRIES):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last = exc
                msg = str(exc).lower()
                if "disk i/o" not in msg and "locked" not in msg and "busy" not in msg:
                    raise
                time.sleep(_IO_RETRY_SLEEP_SEC * (attempt + 1))
        assert last is not None
        raise last

    def _migrate(self) -> None:
        def _run() -> None:
            with self._db:
                self._db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        player_uuid TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        route TEXT,
                        tier TEXT,
                        route_ms INTEGER NOT NULL DEFAULT 0,
                        model_ms INTEGER NOT NULL DEFAULT 0,
                        total_ms INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL,
                        message TEXT NOT NULL DEFAULT '',
                        created_ms INTEGER NOT NULL,
                        updated_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS actions (
                        action_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id),
                        idempotency_key TEXT NOT NULL UNIQUE,
                        tool TEXT NOT NULL,
                        arguments_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        result_json TEXT,
                        created_ms INTEGER NOT NULL,
                        updated_ms INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS jobs_player_idx
                        ON jobs(player_uuid, created_ms DESC);
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_uuid TEXT NOT NULL,
                        job_id TEXT,
                        rating TEXT NOT NULL CHECK (rating IN ('good', 'bad')),
                        note TEXT NOT NULL DEFAULT '',
                        created_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS player_sessions (
                        player_uuid TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        updated_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS job_snapshots (
                        job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                        payload_json TEXT NOT NULL,
                        created_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS request_gaps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_ms INTEGER NOT NULL,
                        player_uuid TEXT NOT NULL DEFAULT '',
                        player_name TEXT NOT NULL DEFAULT '',
                        prompt TEXT NOT NULL DEFAULT '',
                        route TEXT NOT NULL DEFAULT '',
                        tier TEXT NOT NULL DEFAULT '',
                        reason TEXT NOT NULL,
                        message TEXT NOT NULL DEFAULT '',
                        candidates_json TEXT NOT NULL DEFAULT '[]',
                        job_id TEXT
                    );
                    CREATE INDEX IF NOT EXISTS request_gaps_created_idx
                        ON request_gaps(created_ms DESC);
                    CREATE INDEX IF NOT EXISTS request_gaps_reason_idx
                        ON request_gaps(reason, created_ms DESC);
                    """
                )
                columns = {
                    row[1]
                    for row in self._db.execute("PRAGMA table_info(jobs)").fetchall()
                }
                for name, declaration in (
                    ("tier", "TEXT"),
                    ("route_ms", "INTEGER NOT NULL DEFAULT 0"),
                    ("model_ms", "INTEGER NOT NULL DEFAULT 0"),
                    ("total_ms", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    if name not in columns:
                        self._db.execute(
                            f"ALTER TABLE jobs ADD COLUMN {name} {declaration}"
                        )

        self._with_retry(_run)

    def create_job(
        self,
        *,
        job_id: str,
        trace_id: str,
        player_uuid: str,
        prompt: str,
    ) -> None:
        now = int(time.time() * 1000)

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    INSERT INTO jobs
                        (job_id, trace_id, player_uuid, prompt, status, created_ms, updated_ms)
                    VALUES (?, ?, ?, ?, 'running', ?, ?)
                    """,
                    (job_id, trace_id, player_uuid, prompt, now, now),
                )

        self._with_retry(_run)

    def job_prompt(self, job_id: str) -> str | None:
        def _run() -> str | None:
            with self._lock:
                row = self._db.execute(
                    "SELECT prompt FROM jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
            if row is None:
                return None
            return str(row[0] or "")

        return self._with_retry(_run)

    def set_route(
        self,
        job_id: str,
        route: str,
        *,
        tier: str = "",
        route_ms: int = 0,
        model_ms: int = 0,
    ) -> None:
        self._update_job(
            job_id,
            route=route,
            tier=tier,
            route_ms=str(route_ms),
            model_ms=str(model_ms),
        )

    def complete_job(
        self, job_id: str, *, ok: bool, message: str, total_ms: int = 0
    ) -> None:
        self._update_job(
            job_id,
            status="done" if ok else "failed",
            message=message,
            total_ms=str(total_ms),
        )

    def add_action(
        self,
        *,
        action_id: str,
        job_id: str,
        idempotency_key: str,
        tool: str,
        arguments: dict[str, Any],
    ) -> None:
        now = int(time.time() * 1000)

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    INSERT INTO actions
                        (action_id, job_id, idempotency_key, tool, arguments_json,
                         status, created_ms, updated_ms)
                    VALUES (?, ?, ?, ?, ?, 'sent', ?, ?)
                    """,
                    (
                        action_id,
                        job_id,
                        idempotency_key,
                        tool,
                        json.dumps(arguments, separators=(",", ":"), sort_keys=True),
                        now,
                        now,
                    ),
                )

        self._with_retry(_run)

    def complete_action(self, action_id: str, result: dict[str, Any]) -> None:
        now = int(time.time() * 1000)

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    UPDATE actions
                    SET status = ?, result_json = ?, updated_ms = ?
                    WHERE action_id = ?
                    """,
                    (
                        "done" if result.get("ok") else "failed",
                        json.dumps(result, separators=(",", ":"), sort_keys=True),
                        now,
                        action_id,
                    ),
                )

        self._with_retry(_run)

    def action_correlation(self, action_id: str) -> tuple[str, str, int] | None:
        with self._lock:
            row = self._db.execute(
                """
                SELECT actions.job_id, jobs.trace_id, actions.created_ms
                FROM actions
                JOIN jobs ON jobs.job_id = actions.job_id
                WHERE actions.action_id = ?
                """,
                (action_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["job_id"]), str(row["trace_id"]), int(row["created_ms"])

    def record_feedback(
        self, *, player_uuid: str, rating: str, note: str = ""
    ) -> None:
        if rating not in {"good", "bad"}:
            raise ValueError("rating must be good or bad")

        def _run() -> None:
            with self._lock, self._db:
                prior = self._db.execute(
                    """
                    SELECT job_id FROM jobs
                    WHERE player_uuid = ?
                      AND status IN ('done', 'failed')
                      AND COALESCE(route, '') NOT IN ('feedback', 'grammar.cancel')
                    ORDER BY created_ms DESC LIMIT 1
                    """,
                    (player_uuid,),
                ).fetchone()
                self._db.execute(
                    """
                    INSERT INTO feedback (player_uuid, job_id, rating, note, created_ms)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        player_uuid,
                        str(prior["job_id"]) if prior is not None else None,
                        rating,
                        note[:500],
                        int(time.time() * 1000),
                    ),
                )

        self._with_retry(_run)

    def counts(self) -> dict[str, int]:
        with self._lock:
            jobs = self._db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            actions = self._db.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        return {"jobs": int(jobs), "actions": int(actions)}

    def feedback_count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0])

    def record_gap(
        self,
        *,
        reason: str,
        message: str = "",
        job_id: str = "",
        player_uuid: str = "",
        player_name: str = "",
        prompt: str = "",
        route: str = "",
        tier: str = "",
        candidates: list[str] | None = None,
    ) -> None:
        """Append an unfulfilled-request gap row (coverage demand signal)."""
        if reason not in {"clarify", "unresolved", "refuse", "failed", "ingest"}:
            raise ValueError(f"invalid gap reason: {reason}")

        resolved_prompt = prompt
        resolved_route = route
        resolved_tier = tier
        resolved_player = player_uuid
        if job_id and (not resolved_prompt or not resolved_route or not resolved_tier):
            with self._lock:
                row = self._db.execute(
                    """
                    SELECT prompt, route, tier, player_uuid
                    FROM jobs WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
            if row is not None:
                if not resolved_prompt:
                    resolved_prompt = str(row["prompt"] or "")
                if not resolved_route:
                    resolved_route = str(row["route"] or "")
                if not resolved_tier:
                    resolved_tier = str(row["tier"] or "")
                if not resolved_player:
                    resolved_player = str(row["player_uuid"] or "")

        clean_candidates: list[str] = []
        for item in candidates or []:
            text = str(item).strip()
            if text and text not in clean_candidates:
                clean_candidates.append(text)
            if len(clean_candidates) >= 8:
                break

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    INSERT INTO request_gaps (
                        created_ms, player_uuid, player_name, prompt, route, tier,
                        reason, message, candidates_json, job_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(time.time() * 1000),
                        resolved_player[:80],
                        (player_name or "")[:80],
                        (resolved_prompt or "")[:500],
                        (resolved_route or "")[:120],
                        (resolved_tier or "")[:16],
                        reason,
                        (message or "")[:300],
                        json.dumps(clean_candidates, separators=(",", ":")),
                        job_id or None,
                    ),
                )

        self._with_retry(_run)

    def gap_count(self) -> int:
        with self._lock:
            return int(
                self._db.execute("SELECT COUNT(*) FROM request_gaps").fetchone()[0]
            )

    def save_job_snapshot(self, job_id: str, payload: dict[str, Any]) -> None:
        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    INSERT INTO job_snapshots (job_id, payload_json, created_ms)
                    VALUES (?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        created_ms = excluded.created_ms
                    """,
                    (job_id, json.dumps(payload), int(time.time() * 1000)),
                )
                # TTL: drop snapshots older than 14 days.
                cutoff = int(time.time() * 1000) - 14 * 24 * 60 * 60 * 1000
                self._db.execute(
                    "DELETE FROM job_snapshots WHERE created_ms < ?", (cutoff,)
                )

        self._with_retry(_run)

    def live_metrics(self) -> dict[str, float | int]:
        with self._lock:
            jobs = int(self._db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
            undos = int(
                self._db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE route LIKE '%undo%'"
                ).fetchone()[0]
            )
            bads = int(
                self._db.execute(
                    "SELECT COUNT(*) FROM feedback WHERE rating = 'bad'"
                ).fetchone()[0]
            )
            goods = int(
                self._db.execute(
                    "SELECT COUNT(*) FROM feedback WHERE rating = 'good'"
                ).fetchone()[0]
            )
        return {
            "jobs": jobs,
            "undo_jobs": undos,
            "feedback_good": goods,
            "feedback_bad": bads,
            "undo_rate": (undos / jobs) if jobs else 0.0,
            "bad_tag_rate": (bads / max(goods + bads, 1)),
        }

    def load_player_session(self, player_uuid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload_json FROM player_sessions WHERE player_uuid = ?",
                (player_uuid,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def save_player_session(self, player_uuid: str, payload: dict[str, Any]) -> None:
        now = int(time.time() * 1000)

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    """
                    INSERT INTO player_sessions (player_uuid, payload_json, updated_ms)
                    VALUES (?, ?, ?)
                    ON CONFLICT(player_uuid) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_ms = excluded.updated_ms
                    """,
                    (
                        player_uuid,
                        json.dumps(payload, separators=(",", ":"), sort_keys=True),
                        now,
                    ),
                )

        self._with_retry(_run)

    def action_tool_arguments(self, action_id: str) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT tool, arguments_json FROM actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            arguments = json.loads(str(row["arguments_json"]))
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return str(row["tool"]), arguments

    def job_route(self, job_id: str) -> str:
        with self._lock:
            row = self._db.execute(
                "SELECT route FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return str(row["route"] or "") if row is not None else ""

    def metric_snapshot(self) -> dict[str, Any]:
        with self._lock:
            status_rows = self._db.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
            tier_rows = self._db.execute(
                "SELECT tier, COUNT(*) AS count FROM jobs WHERE tier IS NOT NULL GROUP BY tier"
            ).fetchall()
            timing = self._db.execute(
                """
                SELECT
                    COALESCE(AVG(route_ms), 0) AS route_avg,
                    COALESCE(AVG(model_ms), 0) AS model_avg,
                    COALESCE(AVG(total_ms), 0) AS total_avg,
                    COALESCE(MAX(total_ms), 0) AS total_max
                FROM jobs
                WHERE status IN ('done', 'failed')
                """
            ).fetchone()
        return {
            "status": {str(row["status"]): int(row["count"]) for row in status_rows},
            "tier": {str(row["tier"]): int(row["count"]) for row in tier_rows},
            "route_avg_ms": float(timing["route_avg"]),
            "model_avg_ms": float(timing["model_avg"]),
            "total_avg_ms": float(timing["total_avg"]),
            "total_max_ms": int(timing["total_max"]),
        }

    def _update_job(self, job_id: str, **values: str) -> None:
        if not values:
            return
        values["updated_ms"] = str(int(time.time() * 1000))
        assignments = ", ".join(f"{key} = ?" for key in values)

        def _run() -> None:
            with self._lock, self._db:
                self._db.execute(
                    f"UPDATE jobs SET {assignments} WHERE job_id = ?",
                    (*values.values(), job_id),
                )

        self._with_retry(_run)
