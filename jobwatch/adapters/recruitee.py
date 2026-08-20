"""Recruitee adapter.

API: GET https://{token}.recruitee.com/api/offers/
No auth required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import AdapterError, Job

ats_name = "recruitee"

BASE_URL = "https://{token}.recruitee.com/api/offers/"


def _parse_recruitee_date(value: str | None) -> datetime | None:
    """Recruitee dates look like '2026-06-04 14:15:44 UTC', not ISO8601."""
    if not value:
        return None
    try:
        return datetime.strptime(value.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"recruitee:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data.get("offers", []):
        location = item.get("location", "") or ""
        # published_at reflects when the offer actually went live; created_at can
        # be much older if the offer entity was drafted/reused before publishing.
        posted_at = _parse_recruitee_date(item.get("published_at")) or _parse_recruitee_date(
            item.get("created_at")
        )

        departments = item.get("department") or None

        jobs.append(
            Job(
                uid=f"recruitee:{token}:{item['id']}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("title", ""),
                location=location,
                remote=bool(item.get("remote")),
                department=departments,
                url=item.get("careers_url", ""),
                posted_at=posted_at,
                description=item.get("description"),
                salary=None,
                raw=item,
            )
        )
    return jobs
