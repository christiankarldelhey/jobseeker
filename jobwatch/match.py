"""Scoring engine driven entirely by config.yaml (no hardcoded keywords)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .adapters.base import Job


@dataclass
class MatchConfig:
    hard_exclude: list[str]
    stack: dict[str, int]
    seniority: dict[str, int]
    geo: dict[str, int]
    immediate_threshold: int
    digest_threshold: int
    stale_after_days: int | None
    max_age_days: int | None

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "MatchConfig":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        thresholds = raw.get("thresholds", {})
        return cls(
            hard_exclude=[s.lower() for s in raw.get("hard_exclude", [])],
            stack={k.lower(): v for k, v in raw.get("stack", {}).items()},
            seniority={k.lower(): v for k, v in raw.get("seniority", {}).items()},
            geo={k.lower(): v for k, v in raw.get("geo", {}).items()},
            immediate_threshold=thresholds.get("immediate", 8),
            digest_threshold=thresholds.get("digest", 5),
            stale_after_days=raw.get("stale_after_days"),
            max_age_days=raw.get("max_age_days"),
        )


def _title_haystack(job: Job) -> str:
    """Title + department only -- used to gate whether a role is even in-scope.
    Deliberately excludes the full description, which often contains generic
    company/tech boilerplate ("we build with React...") on unrelated roles
    (Sales, Marketing, PM), which would otherwise cause false positives."""
    parts = [job.title or "", job.department or ""]
    return " ".join(parts).lower()


def _full_haystack(job: Job) -> str:
    parts = [job.title or "", job.location or "", job.department or "", job.description or ""]
    return " ".join(parts).lower()


def is_excluded(job: Job, cfg: MatchConfig) -> bool:
    text = _full_haystack(job)
    return any(term in text for term in cfg.hard_exclude)


def score(job: Job, cfg: MatchConfig) -> int:
    if is_excluded(job, cfg):
        return -1

    title_text = _title_haystack(job)
    title_stack_score = sum(weight for keyword, weight in cfg.stack.items() if keyword in title_text)
    if title_stack_score == 0:
        # The job title/department itself carries no technical stack signal ->
        # not a relevant role for this profile, regardless of what boilerplate
        # tech mentions show up buried in the full description.
        return 0

    text = _full_haystack(job)
    stack_score = sum(weight for keyword, weight in cfg.stack.items() if keyword in text)

    total = stack_score
    for bucket in (cfg.seniority, cfg.geo):
        for keyword, weight in bucket.items():
            if keyword in text:
                total += weight
    if job.remote:
        total += 1
    return total


def _age_days(job: Job) -> int | None:
    """Returns the job's age in days, or None if posted_at is unknown."""
    if job.posted_at is None:
        return None
    return (datetime.now(timezone.utc) - job.posted_at).days


def is_too_old(job: Job, cfg: MatchConfig) -> bool:
    """True if the job has a known posted_at older than max_age_days.
    Jobs with no date at all (posted_at is None) are NOT filtered out here --
    we can't verify their age one way or the other, so they pass through."""
    age_days = _age_days(job)
    if not cfg.max_age_days or age_days is None:
        return False
    return age_days > cfg.max_age_days


def is_stale(job: Job, cfg: MatchConfig) -> bool:
    """True if the job is older than stale_after_days (but not yet too_old).
    Jobs with unknown posted_at are never considered stale."""
    age_days = _age_days(job)
    if not cfg.stale_after_days or age_days is None:
        return False
    return age_days > cfg.stale_after_days


def classify(job: Job, cfg: MatchConfig) -> str:
    """Returns 'immediate', 'digest', 'ignore', 'excluded', or 'too_old'."""
    s = score(job, cfg)
    if s < 0:
        return "excluded"
    if is_too_old(job, cfg):
        return "too_old"
    if s >= cfg.immediate_threshold:
        # A strong match that's gotten stale gets demoted to the daily digest
        # instead of being dropped outright -- still worth applying to if it's
        # still open, just not urgent enough to interrupt you.
        return "digest" if is_stale(job, cfg) else "immediate"
    if s >= cfg.digest_threshold:
        return "digest"
    return "ignore"
