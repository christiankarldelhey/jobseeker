"""Greenhouse adapter.

API: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
No auth required.
"""

from __future__ import annotations

from datetime import datetime

import requests

from .base import AdapterError, Job

ats_name = "greenhouse"

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, params={"content": "true"}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"greenhouse:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data.get("jobs", []):
        location = (item.get("location") or {}).get("name", "") or ""
        departments = item.get("departments") or []
        department = departments[0]["name"] if departments else None
        posted_at = None
        if item.get("updated_at"):
            try:
                posted_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None

        jobs.append(
            Job(
                uid=f"greenhouse:{token}:{item['id']}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("title", ""),
                location=location,
                remote="remote" in location.lower(),
                department=department,
                url=item.get("absolute_url", ""),
                posted_at=posted_at,
                description=item.get("content"),
                salary=None,
                raw=item,
            )
        )
    return jobs
