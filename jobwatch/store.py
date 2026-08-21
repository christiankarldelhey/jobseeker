"""SQLite persistence: dedup of seen jobs + health log of each poller run."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adapters.base import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    uid TEXT PRIMARY KEY,
    ats TEXT,
    token TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT,
    posted_at TEXT,
    first_seen TEXT,
    last_seen TEXT,
    active INTEGER DEFAULT 1,
    score INTEGER DEFAULT 0,
    notified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    ats TEXT,
    token TEXT,
    ok INTEGER,
    n INTEGER,
    error TEXT
);
"""


@dataclass
class DiffResult:
    new_jobs: list[Job]
    closed_uids: list[str]


class Store:
    def __init__(self, db_path: str | Path = "jobwatch.db"):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Adds columns introduced after the initial schema, for pre-existing DBs."""
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(seen)")}
        if "posted_at" not in existing_cols:
            conn.execute("ALTER TABLE seen ADD COLUMN posted_at TEXT")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record_run(self, ats: str, token: str, ok: bool, n: int, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (ts, ats, token, ok, n, error) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), ats, token, int(ok), n, error),
            )

    def diff_and_update(self, ats: str, token: str, current_jobs: list[Job]) -> DiffResult:
        """Compares current_jobs for a given (ats, token) against what's stored,
        updates the DB, and returns which ones are new vs. which uids closed."""
        now = datetime.now(timezone.utc).isoformat()
        current_uids = {job.uid for job in current_jobs}

        with self._connect() as conn:
            existing_active = {
                row[0]
                for row in conn.execute(
                    "SELECT uid FROM seen WHERE ats = ? AND token = ? AND active = 1",
                    (ats, token),
                )
            }

            new_jobs = [job for job in current_jobs if job.uid not in existing_active]
            closed_uids = list(existing_active - current_uids)

            for job in current_jobs:
                posted_at_iso = job.posted_at.isoformat() if job.posted_at else None
                conn.execute(
                    """
                    INSERT INTO seen (uid, ats, token, company, title, location, url, posted_at, first_seen, last_seen, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(uid) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        active = 1
                    """,
                    (job.uid, job.ats, job.token, job.company, job.title, job.location, job.url, posted_at_iso, now, now),
                )

            for uid in closed_uids:
                conn.execute("UPDATE seen SET active = 0, last_seen = ? WHERE uid = ?", (now, uid))

        return DiffResult(new_jobs=new_jobs, closed_uids=closed_uids)

    def mark_notified(self, uid: str, score: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE seen SET notified = 1, score = ? WHERE uid = ?", (score, uid))

    def update_score(self, uid: str, score: int) -> None:
        """Persists a score without marking the job as notified (used for digest queue)."""
        with self._connect() as conn:
            conn.execute("UPDATE seen SET score = ? WHERE uid = ?", (score, uid))

    def mark_digest_sent(self, uids: list[str]) -> None:
        if not uids:
            return
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in uids)
            conn.execute(f"UPDATE seen SET notified = 1 WHERE uid IN ({placeholders})", uids)

    def pending_digest(self) -> list[sqlite3.Row]:
        """Jobs with a mid score that were stored but not yet emailed in a digest."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM seen WHERE active = 1 AND notified = 0 AND score > 0"
            ).fetchall()

    def recent_run_health(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def consecutive_failures(self, ats: str, token: str, limit: int = 20) -> int:
        """Counts how many of the most recent runs for this (ats, token) failed
        in a row, stopping at the first success. Used to alert only on a
        sustained break (e.g. a site redesign) rather than a single transient
        network blip."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ok FROM runs WHERE ats = ? AND token = ? ORDER BY id DESC LIMIT ?",
                (ats, token, limit),
            ).fetchall()
        streak = 0
        for (ok,) in rows:
            if ok:
                break
            streak += 1
        return streak

    def consecutive_empty_results(self, ats: str, token: str, limit: int = 20) -> int:
        """Counts how many of the most recent SUCCESSFUL runs for this
        (ats, token) returned zero jobs in a row. Catches silent breakage
        (e.g. an HTML-scraping adapter whose selectors stop matching after a
        site redesign, without raising an exception)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ok, n FROM runs WHERE ats = ? AND token = ? ORDER BY id DESC LIMIT ?",
                (ats, token, limit),
            ).fetchall()
        streak = 0
        for ok, n in rows:
            if not ok:
                break
            if n > 0:
                break
            streak += 1
        return streak
