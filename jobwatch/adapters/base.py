"""Common data model and interface shared by every ATS adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Job:
    """Normalized job posting, regardless of which ATS it came from."""

    uid: str  # f"{ats}:{token}:{native_id}" -- the dedup key
    ats: str
    token: str
    company: str
    title: str
    location: str
    remote: bool
    department: str | None
    url: str
    posted_at: datetime | None
    description: str | None
    salary: str | None
    raw: dict = field(default_factory=dict, compare=False, repr=False)


class Adapter(Protocol):
    """Every adapter module must expose a `fetch(token: str) -> list[Job]` function."""

    ats_name: str

    def fetch(self, token: str) -> list[Job]: ...


class AdapterError(Exception):
    """Raised when an adapter fails to fetch or parse jobs for a given token."""
