"""SmartRecruiters adapter.

API: GET https://api.smartrecruiters.com/v1/companies/{token}/postings
No auth required.
"""

from __future__ import annotations

from datetime import datetime

import requests

from .base import AdapterError, Job

ats_name = "smartrecruiters"

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{token}/postings"


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"smartrecruiters:{token} fetch failed: {exc}") from exc

    data = resp.json()
    jobs: list[Job] = []
    for item in data.get("content", []):
        loc = item.get("location") or {}
        location = ", ".join(filter(None, [loc.get("city"), loc.get("country")]))
        posted_at = None
        if item.get("releasedDate"):
            try:
                posted_at = datetime.fromisoformat(item["releasedDate"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None

        department = (item.get("department") or {}).get("label")
        job_id = item.get("id")

        jobs.append(
            Job(
                uid=f"smartrecruiters:{token}:{job_id}",
                ats=ats_name,
                token=token,
                company=token,
                title=item.get("name", ""),
                location=location,
                remote=bool(loc.get("remote")),
                department=department,
                url=f"https://jobs.smartrecruiters.com/{token}/{job_id}",
                posted_at=posted_at,
                description=None,
                salary=None,
                raw=item,
            )
        )
    return jobs
