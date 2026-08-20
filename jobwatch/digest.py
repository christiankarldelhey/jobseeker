"""Sends the daily digest of mid-score jobs queued by run.py.

Usage:
    python -m jobwatch.digest
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from . import notify
from .adapters.base import Job
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv()
    store = Store(ROOT / "jobwatch.db")

    rows = store.pending_digest()
    if not rows:
        print("No pending digest items.")
        return 0

    jobs_with_scores: list[tuple[Job, int]] = []
    for row in rows:
        posted_at = None
        if row["posted_at"]:
            try:
                posted_at = datetime.fromisoformat(row["posted_at"])
            except ValueError:
                posted_at = None

        job = Job(
            uid=row["uid"],
            ats=row["ats"],
            token=row["token"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            remote=False,
            department=None,
            url=row["url"],
            posted_at=posted_at,
            description=None,
            salary=None,
        )
        jobs_with_scores.append((job, row["score"]))

    notify.send_digest(jobs_with_scores)
    store.mark_digest_sent([row["uid"] for row in rows])
    print(f"Digest sent with {len(jobs_with_scores)} job(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
