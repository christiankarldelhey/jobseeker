"""Personio adapter.

API: GET https://{token}.jobs.personio.de/xml
Returns XML (not JSON), no auth required. Very common in Spain/DACH.
"""

from __future__ import annotations

from xml.etree import ElementTree

import requests

from .base import AdapterError, Job

ats_name = "personio"

BASE_URL = "https://{token}.jobs.personio.de/xml"


def _text(el, tag: str) -> str:
    node = el.find(tag)
    return node.text.strip() if node is not None and node.text else ""


def fetch(token: str, timeout: int = 15) -> list[Job]:
    url = BASE_URL.format(token=token)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"personio:{token} fetch failed: {exc}") from exc

    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as exc:
        raise AdapterError(f"personio:{token} XML parse failed: {exc}") from exc

    jobs: list[Job] = []
    for position in root.findall(".//position"):
        job_id = _text(position, "id")
        office = _text(position, "office")
        department = _text(position, "department") or None
        name = _text(position, "name")
        remote = "remote" in office.lower() or "remote" in name.lower()

        jobs.append(
            Job(
                uid=f"personio:{token}:{job_id}",
                ats=ats_name,
                token=token,
                company=token,
                title=name,
                location=office,
                remote=remote,
                department=department,
                url=_text(position, "careerSiteUrl") or f"https://{token}.jobs.personio.de/job/{job_id}",
                posted_at=None,
                description=_text(position, "jobDescriptions") or None,
                salary=None,
                raw={child.tag: (child.text or "") for child in position},
            )
        )
    return jobs
