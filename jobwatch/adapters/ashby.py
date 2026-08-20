"""Ashby adapter.

API: GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true
No auth required.
"""

from __future__ import annotations

from datetime import datetime

import requests

from .base import AdapterError, Job

ats_name = "ashby"

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, params={"includeCompensation": "true"}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"ashby:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data.get("jobs", []):
        posted_at = None
        if item.get("publishedAt"):
            try:
                posted_at = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None

        comp = item.get("compensation") or {}
        salary = comp.get("compensationTierSummary") or comp.get("summary")

        jobs.append(
            Job(
                uid=f"ashby:{token}:{item['id']}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("title", ""),
                location=item.get("location", "") or "",
                remote=bool(item.get("isRemote")),
                department=item.get("department"),
                url=item.get("jobUrl", ""),
                posted_at=posted_at,
                description=item.get("descriptionPlain") or item.get("descriptionHtml"),
                salary=salary,
                raw=item,
            )
        )
    return jobs
