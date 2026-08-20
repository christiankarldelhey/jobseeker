"""Lever adapter.

API: GET https://api.lever.co/v0/postings/{token}?mode=json
No auth required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from .base import AdapterError, Job

ats_name = "lever"

BASE_URL = "https://api.lever.co/v0/postings/{token}"


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, params={"mode": "json"}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"lever:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data:
        categories = item.get("categories") or {}
        location = categories.get("location", "") or ""
        posted_at = None
        if item.get("createdAt"):
            try:
                posted_at = datetime.fromtimestamp(item["createdAt"] / 1000, tz=timezone.utc)
            except (ValueError, OSError):
                posted_at = None

        jobs.append(
            Job(
                uid=f"lever:{token}:{item['id']}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("text", ""),
                location=location,
                remote="remote" in location.lower(),
                department=categories.get("team"),
                url=item.get("hostedUrl", ""),
                posted_at=posted_at,
                description=item.get("descriptionPlain") or item.get("description"),
                salary=None,
                raw=item,
            )
        )
    return jobs
