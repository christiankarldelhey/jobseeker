"""Maps an ATS name (as used in registry.yaml) to its adapter module."""

from __future__ import annotations

from . import ashby, greenhouse, lever, personio, recruitee, smartrecruiters, workable

ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "recruitee": recruitee,
    "smartrecruiters": smartrecruiters,
    "personio": personio,
}


def get_adapter(ats: str):
    try:
        return ADAPTERS[ats]
    except KeyError as exc:
        raise ValueError(f"Unknown ATS '{ats}'. Known: {sorted(ADAPTERS)}") from exc
