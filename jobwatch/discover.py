"""Best-effort discovery of (ats, token) for a company, given its domain.

Usage:
    python -m jobwatch.discover typeform.com holded.com ...

Writes resolved entries to stdout (append them to registry.yaml yourself)
and unresolved domains to unresolved.csv.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
UNRESOLVED_CSV = ROOT / "unresolved.csv"

CAREERS_PATHS = ["/careers", "/jobs", "/empleo", "/trabaja-con-nosotros", "/join-us", "/about/careers"]

# Token slugs are always a restricted charset (alnum, dash, underscore, dot) --
# capturing anything wider than this picks up surrounding HTML/CSS by accident.
TOKEN = r"[A-Za-z0-9_.-]+"

# (regex on final URL host+path) -> ats
URL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"job-boards\.greenhouse\.io/({TOKEN})"), "greenhouse"),
    (re.compile(rf"boards\.greenhouse\.io/({TOKEN})"), "greenhouse"),
    (re.compile(rf"jobs\.lever\.co/({TOKEN})"), "lever"),
    (re.compile(rf"jobs\.ashbyhq\.com/({TOKEN})"), "ashby"),
    (re.compile(rf"apply\.workable\.com/({TOKEN})"), "workable"),
    (re.compile(rf"({TOKEN})\.recruitee\.com"), "recruitee"),
    (re.compile(rf"({TOKEN})\.jobs\.personio\.(?:de|com)"), "personio"),
    (re.compile(rf"jobs\.smartrecruiters\.com/({TOKEN})"), "smartrecruiters"),
]

# Fallback: same patterns, but scanned only inside href="..." attributes of the
# HTML, never in free text (avoids swallowing unrelated CSS/JS around a match).
HREF_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf'href="[^"]*job-boards\.greenhouse\.io/({TOKEN})[^"]*"'), "greenhouse"),
    (re.compile(rf'href="[^"]*boards\.greenhouse\.io/({TOKEN})[^"]*"'), "greenhouse"),
    (re.compile(rf'href="[^"]*jobs\.lever\.co/({TOKEN})[^"]*"'), "lever"),
    (re.compile(rf'href="[^"]*jobs\.ashbyhq\.com/({TOKEN})[^"]*"'), "ashby"),
    (re.compile(rf'href="[^"]*apply\.workable\.com/({TOKEN})[^"]*"'), "workable"),
    (re.compile(rf'href="[^"]*({TOKEN})\.recruitee\.com[^"]*"'), "recruitee"),
    (re.compile(rf'href="[^"]*({TOKEN})\.jobs\.personio\.(?:de|com)[^"]*"'), "personio"),
    (re.compile(rf'href="[^"]*jobs\.smartrecruiters\.com/({TOKEN})[^"]*"'), "smartrecruiters"),
]


def _validate(ats: str, token: str) -> bool:
    """Confirms the (ats, token) pair actually resolves to a job board with postings."""
    from .adapters.base import AdapterError
    from .adapters.registry import get_adapter

    try:
        jobs = get_adapter(ats).fetch(token)
        return len(jobs) > 0
    except (AdapterError, ValueError, Exception):
        return False


def _try_url(url: str, timeout: int = 10) -> tuple[str, str] | None:
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None

    final_url = resp.url
    for pattern, ats in URL_PATTERNS:
        m = pattern.search(final_url)
        if m:
            return ats, m.group(1)

    if resp.ok:
        for pattern, ats in HREF_PATTERNS:
            m = pattern.search(resp.text)
            if m:
                return ats, m.group(1)

    return None


def resolve(domain: str) -> tuple[str, str] | None:
    domain = domain.strip()
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    parsed = urlparse(domain)
    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in CAREERS_PATHS:
        result = _try_url(base + path)
        if result and _validate(*result):
            return result
    return None


def main(domains: list[str]) -> int:
    resolved: list[tuple[str, str, str]] = []
    unresolved: list[str] = []

    for domain in domains:
        result = resolve(domain)
        if result:
            ats, token = result
            resolved.append((domain, ats, token))
            print(f"  - company: {domain}\n    ats: {ats}\n    token: {token}")
        else:
            unresolved.append(domain)
            print(f"[unresolved] {domain}", file=sys.stderr)

    if unresolved:
        write_header = not UNRESOLVED_CSV.exists()
        with open(UNRESOLVED_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["domain"])
            for d in unresolved:
                writer.writerow([d])

    print(f"\nResolved {len(resolved)}/{len(domains)}. Unresolved appended to {UNRESOLVED_CSV.name}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m jobwatch.discover <domain> [domain ...]", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1:]))
