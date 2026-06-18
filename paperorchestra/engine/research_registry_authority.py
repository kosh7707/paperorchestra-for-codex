from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper

_AUTHORITATIVE_PRIOR_MARKERS = (
    "rfc editor",
    "rfc ",
    "rfc-",
    "rfc/",
    "10.17487/rfc",
    "nist",
    "fips",
    "sp 800",
    "10.6028/nist",
)


def prior_work_metadata_is_authoritative(prior: VerifiedPaper) -> bool:
    """Return true when curated source metadata is more canonical than live paper search."""

    origin = str(prior.origin or "").lower()
    venue = str(prior.venue or "").lower()
    url = str(prior.url or "").lower()
    doi = " ".join(str(value).lower() for value in (prior.external_ids or {}).values())
    return any(marker in " ".join([origin, venue, url, doi]) for marker in _AUTHORITATIVE_PRIOR_MARKERS)


def merge_authoritative_external_ids(
    prior_external_ids: dict[str, str],
    verified_external_ids: dict[str, str],
) -> dict[str, str]:
    merged = dict(prior_external_ids)
    for key, value in verified_external_ids.items():
        if key not in merged:
            merged[key] = value
            continue
        if merged[key] == value:
            continue
        _store_verified_external_id_conflict(merged, key, value)
    return merged


def _store_verified_external_id_conflict(merged: dict[str, str], key: str, value: str) -> None:
    conflict_key = f"Verified{key}"
    suffix = 2
    while conflict_key in merged and merged[conflict_key] != value:
        conflict_key = f"Verified{key}{suffix}"
        suffix += 1
    merged.setdefault(conflict_key, value)
