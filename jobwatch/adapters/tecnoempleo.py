"""Tecnoempleo adapter.

Tecnoempleo is a Spanish IT job board, not a per-company ATS -- there's no
self-serve JSON/RSS API (they require contacting them manually for API
access), so this scrapes the public, unauthenticated search-results HTML
page. That page is NOT blocked by robots.txt (only the personalized,
login-gated alert RSS is), and requires no login/cookies.

`token` here is a comma-separated list of search keywords (e.g.
"vue,react native,frontend") instead of a company slug -- each keyword is
queried independently and results are merged, deduped by their native
"rf-<hash>" reference id.

Note: `uid` is deliberately independent of `token` (unlike other adapters)
so that editing the keyword list later doesn't change job identity for
postings already seen -- only the age of the whole `token` string affects
which store row is used for the "still open on this ATS" tracking, so
changing the keyword list can cause a one-time re-notification of jobs
still showing up under the new keyword set. That's an accepted, rare
trade-off for keeping this a single registry entry (single email batch)
instead of one entry per keyword.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from .base import AdapterError, Job

ats_name = "tecnoempleo"

SEARCH_URL = "https://www.tecnoempleo.com/ofertas-trabajo/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobWatch/1.0; +https://github.com/)"}

# Site's own "Modalidad de trabajo" filter values: 1 = 100% remote, 3 = hybrid.
# Excludes 2 (on-site) and 4 (unspecified) to match this profile's geo preferences.
REMOTE_MODALITY_PARAM = ",1,3,"


def _parse_date(text: str) -> datetime | None:
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def _fetch_keyword(keyword: str, timeout: int) -> list[Job]:
    params = {"te": keyword, "en_remoto": REMOTE_MODALITY_PARAM}
    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"tecnoempleo:{keyword} fetch failed: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs: list[Job] = []

    for card in soup.select("div.p-3.border.rounded.mb-3.bg-white"):
        onclick = card.get("onclick", "")
        url_match = re.search(r"location\.href='([^']+)'", onclick)
        if not url_match:
            continue
        url = url_match.group(1)
        rf_match = re.search(r"(rf-[0-9a-f]+)$", url)
        if not rf_match:
            continue
        rf_id = rf_match.group(1)

        title_tag = card.select_one("h3.fs-5 a")
        title = title_tag.get_text(strip=True) if title_tag else ""

        company_tag = card.select_one("a.text-primary.link-muted")
        company = company_tag.get_text(strip=True) if company_tag else "Tecnoempleo"

        meta_div = card.select_one("div.col-12.col-lg-3")
        meta_text = meta_div.get_text(" ", strip=True) if meta_div else ""
        posted_at = _parse_date(meta_text)
        location_tag = meta_div.select_one("b") if meta_div else None
        location = location_tag.get_text(strip=True) if location_tag else ""

        tech_badges = [b.get_text(strip=True) for b in card.select("span.badge")]
        description = " ".join(tech_badges)

        jobs.append(
            Job(
                uid=f"tecnoempleo:{rf_id}",
                ats=ats_name,
                token=keyword,
                company=company,
                title=title,
                location=location,
                remote=True,
                department=None,
                url=url,
                posted_at=posted_at,
                description=description,
                salary=None,
                raw={"keyword": keyword},
            )
        )
    return jobs


def fetch(token: str, timeout: int = 15) -> list[Job]:
    keywords = [k.strip() for k in token.split(",") if k.strip()]
    if not keywords:
        raise AdapterError("tecnoempleo: no keywords configured in token")

    seen_uids: set[str] = set()
    jobs: list[Job] = []
    for keyword in keywords:
        for job in _fetch_keyword(keyword, timeout):
            if job.uid in seen_uids:
                continue
            seen_uids.add(job.uid)
            jobs.append(job)
    return jobs
