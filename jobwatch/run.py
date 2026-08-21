"""Orchestrator: fetch every company in registry.yaml -> diff -> score -> notify.

Usage:
    python -m jobwatch.run
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .adapters.base import AdapterError, Job
from .adapters.registry import get_adapter
from .match import MatchConfig, classify, score as score_job
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def load_registry(path: str | Path = ROOT / "registry.yaml") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", [])


def main() -> int:
    load_dotenv()

    registry = load_registry()
    match_cfg = MatchConfig.load(ROOT / "config.yaml")
    # JOBWATCH_DB_PATH lets you point at a scratch copy of jobwatch.db for
    # testing (e.g. dry runs) without marking real jobs as seen/notified.
    db_path = os.environ.get("JOBWATCH_DB_PATH", str(ROOT / "jobwatch.db"))
    store = Store(db_path)

    notify_enabled = True
    try:
        from . import notify
    except Exception as exc:  # pragma: no cover - import-time guard
        print(f"[warn] notify module unavailable: {exc}", file=sys.stderr)
        notify_enabled = False

    # Consecutive-failure threshold before flagging a source as broken in the
    # email -- avoids alerting on a single transient network hiccup.
    FAILURE_ALERT_THRESHOLD = 2

    immediate_items: list[tuple[Job, int]] = []
    digest_items: list[tuple[Job, int]] = []
    alerts: list[str] = []

    for entry in registry:
        company = entry["company"]
        ats = entry["ats"]
        token = entry["token"]

        try:
            adapter = get_adapter(ats)
            jobs = adapter.fetch(token)
        except (AdapterError, ValueError) as exc:
            print(f"[error] {company} ({ats}:{token}): {exc}", file=sys.stderr)
            store.record_run(ats, token, ok=False, n=0, error=str(exc))
            streak = store.consecutive_failures(ats, token)
            if streak >= FAILURE_ALERT_THRESHOLD:
                alerts.append(
                    f"{company} ({ats}:{token}) lleva {streak} corridas seguidas fallando. "
                    f"Último error: {exc}"
                )
            continue

        store.record_run(ats, token, ok=True, n=len(jobs))
        if len(jobs) == 0:
            empty_streak = store.consecutive_empty_results(ats, token)
            if empty_streak >= FAILURE_ALERT_THRESHOLD:
                alerts.append(
                    f"{company} ({ats}:{token}) lleva {empty_streak} corridas seguidas "
                    f"devolviendo 0 ofertas -- puede que el sitio haya cambiado y el "
                    f"adapter dejó de encontrar resultados en silencio."
                )

        diff = store.diff_and_update(ats, token, jobs)

        for job in diff.new_jobs:
            s = score_job(job, match_cfg)
            verdict = classify(job, match_cfg)
            print(f"[new] {company} — {job.title} (score={s}, verdict={verdict})")

            if verdict == "immediate":
                store.update_score(job.uid, s)
                immediate_items.append((job, s))
            elif verdict == "digest":
                store.update_score(job.uid, s)  # queued; jobwatch.digest sends these later
                digest_items.append((job, s))

        if diff.closed_uids:
            print(f"[closed] {company}: {len(diff.closed_uids)} offer(s) no longer listed")

    if (immediate_items or alerts) and notify_enabled:
        try:
            notify.send_batch(immediate_items, alerts=alerts)
            for job, s in immediate_items:
                store.mark_notified(job.uid, s)
        except Exception as exc:
            print(f"[error] failed to send batch email: {exc}", file=sys.stderr)

    print(
        f"Done. {len(immediate_items)} immediate job(s), {len(alerts)} alert(s) "
        f"({'email sent' if (immediate_items or alerts) else 'no email sent'}), "
        f"{len(digest_items)} queued for digest."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
