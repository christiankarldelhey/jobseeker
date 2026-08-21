"""Manfred (getmanfred.com) adapter.

Like Tecnoempleo, Manfred is a Spanish job board, not a per-company ATS.
Its robots.txt is wide open (`Allow: /` for all bots) and it publishes a
dedicated sitemap of every active offer with an exact lastmod timestamp:
https://www.getmanfred.com/sitemap-offers.xml

Each individual offer page is a Next.js SSR page that embeds a full,
structured JSON payload in a `__NEXT_DATA__` script tag -- no fragile CSS
scraping needed for the actual job data, just JSON key access.

To avoid fetching hundreds of individual offer pages every run (the sitemap
lists ALL categories, not just tech), this does a cheap pre-filter on the
URL slug (which encodes company + role, e.g. "wuolah-backend-engineer-jul26")
against `token` (a comma-separated keyword list, same convention as the
tecnoempleo adapter) before fetching the full JSON for a candidate.

`uid` is the offer's numeric id (independent of `token`, same reasoning as
the tecnoempleo adapter: keyword-list edits shouldn't churn identity for
jobs already seen).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import requests

from .base import AdapterError, Job

ats_name = "manfred"

SITEMAP_URL = "https://www.getmanfred.com/sitemap-offers.xml"
BASE_URL = "https://www.getmanfred.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobWatch/1.0; +https://github.com/)"}

# The sitemap includes every offer ever posted (all categories, not just
# tech), including long-closed ones. Only bother fetching the full JSON for
# entries updated recently -- keeps this to a handful of requests per run
# instead of walking the whole multi-thousand-entry sitemap every time.
SITEMAP_FRESHNESS_DAYS = 60

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def _fetch_sitemap(timeout: int) -> list[tuple[str, str, datetime | None]]:
    """Returns a list of (url, slug, lastmod) for every offer in the sitemap."""
    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AdapterError(f"manfred sitemap fetch failed: {exc}") from exc

    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as exc:
        raise AdapterError(f"manfred sitemap parse failed: {exc}") from exc

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries: list[tuple[str, str, datetime | None]] = []
    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not loc_el.text:
            continue
        url = loc_el.text.strip()
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        lastmod_el = url_el.find("sm:lastmod", ns)
        lastmod = _parse_iso(lastmod_el.text.strip()) if lastmod_el is not None and lastmod_el.text else None
        entries.append((url, slug, lastmod))
    return entries


def _slug_matches(slug: str, keywords: list[str]) -> bool:
    normalized = slug.replace("-", " ").lower()
    return any(kw in normalized for kw in keywords)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_offer(url: str, timeout: int) -> Job | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        offer = data["props"]["pageProps"]["offer"]
    except (json.JSONDecodeError, KeyError):
        return None

    if offer.get("status") == "CLOSED" or offer.get("active") is False:
        return None

    posted_at = None
    jsonld_raw = offer.get("jsonld")
    description = ""
    if jsonld_raw:
        try:
            jsonld = json.loads(jsonld_raw)
            posted_at = _parse_iso(jsonld.get("datePosted"))
            description = jsonld.get("description", "") or ""
        except json.JSONDecodeError:
            pass
    if posted_at is None:
        posted_at = _parse_iso(offer.get("updatedAt"))

    intro = (offer.get("skillsSectionData") or {}).get("intro", "") or ""
    full_description = f"{description} {intro}".strip()

    remote_pct = offer.get("remote") or 0
    is_remote = remote_pct >= 100
    if is_remote:
        location = "Remoto"
    else:
        cities = (offer.get("locationsSummary") or {}).get("trimmedCitiesStr") or ""
        location = cities or ("Híbrido" if remote_pct > 0 else "Presencial")

    return Job(
        uid=f"manfred:{offer['id']}",
        ats=ats_name,
        token=str(offer["id"]),
        company=offer.get("company", "Manfred"),
        title=offer.get("title", ""),
        location=location,
        remote=is_remote,
        department=None,
        url=f"{BASE_URL}{offer['url']}" if offer.get("url", "").startswith("/") else offer.get("url", url),
        posted_at=posted_at,
        description=full_description,
        salary=(
            f"{offer.get('currency', '')}{offer.get('salaryMin', '')}-{offer.get('salaryMax', '')}K"
            if offer.get("salaryMin")
            else None
        ),
        raw={},
    )


def fetch(token: str, timeout: int = 15) -> list[Job]:
    keywords = [k.strip().lower() for k in token.split(",") if k.strip()]
    if not keywords:
        raise AdapterError("manfred: no keywords configured in token")

    cutoff = datetime.now(timezone.utc) - timedelta(days=SITEMAP_FRESHNESS_DAYS)
    entries = _fetch_sitemap(timeout)
    candidates = [
        (url, slug)
        for url, slug, lastmod in entries
        if _slug_matches(slug, keywords) and (lastmod is None or lastmod >= cutoff)
    ]

    jobs: list[Job] = []
    for i, (url, _slug) in enumerate(candidates):
        if i > 0:
            time.sleep(1)  # be polite -- avoid tripping their rate limiting
        job = _fetch_offer(url, timeout)
        if job is not None:
            jobs.append(job)
    return jobs
