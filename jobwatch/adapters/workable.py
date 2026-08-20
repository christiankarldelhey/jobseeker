"""Workable adapter.

API: GET https://apply.workable.com/api/v1/widget/accounts/{token}
No auth required.
"""

from __future__ import annotations

from datetime import datetime

import requests

from .base import AdapterError, Job

ats_name = "workable"

BASE_URL = "https://apply.workable.com/api/v1/widget/accounts/{token}"


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"workable:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data.get("jobs", []):
        loc = item.get("location") or {}
        location = ", ".join(filter(None, [loc.get("city"), loc.get("country")]))
        posted_at = None
        if item.get("created_at"):
            try:
                posted_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None

        shortcode = item.get("shortcode", "")
        jobs.append(
            Job(
                uid=f"workable:{token}:{shortcode}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("title", ""),
                location=location,
                remote=bool(item.get("telecommuting")),
                department=item.get("department"),
                url=item.get("url") or f"https://apply.workable.com/{token}/j/{shortcode}/",
                posted_at=posted_at,
                description=None,
                salary=None,
                raw=item,
            )
        )
    return jobs
