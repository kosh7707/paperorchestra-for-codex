from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.manuscript.citations import extract_citation_keys


def _mock_registry_entry_count(registry_path: str | Path | None) -> int:
    if not registry_path:
        return 0
    candidate = Path(registry_path)
    if not candidate.exists():
        return 0
    try:
        payload = read_json(candidate)
    except Exception:
        return 0
    count = 0
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            if _registry_entry_is_mock(item):
                count += 1
    return count


def _registry_entry_has_live_verification(item: dict[str, Any]) -> bool:
    """Return whether a citation-registry entry was actually live-verified.

    The registry's ``origin`` field can combine curated seed provenance and live
    discovery buckets, for example ``metadata_seed_for_live_verification`` after
    import and ``metadata_seed_for_live_verification+macro_candidates`` after a
    later Semantic Scholar match.  A bare seed label must not be counted as live
    evidence merely because it contains the word "live"; it is live only when a
    non-mock entry includes a real live verification bucket.
    """
    paper_id = str(item.get("paper_id") or "")
    if paper_id.startswith("mock-"):
        return False
    origin_tokens = {
        token.strip().lower()
        for token in re.split(r"[+,;]", str(item.get("origin") or ""))
        if token.strip()
    }
    live_buckets = {"macro_candidates", "micro_candidates"}
    return bool(origin_tokens & live_buckets)


def _registry_entry_is_mock(item: dict[str, Any]) -> bool:
    paper_id = str(item.get("paper_id") or "")
    authors = item.get("authors") or []
    venue = str(item.get("venue") or "")
    return paper_id.startswith("mock-") or authors == ["Mock Author"] or venue == "Mock Venue"


def _registry_entry_key_aliases(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("bibtex_key", "key"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    aliases = item.get("alias_bibtex_keys")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                keys.add(alias.strip())
    return keys


def _registry_entry_has_mixed_non_live_provenance(item: dict[str, Any]) -> bool:
    """Return whether a cited entry has usable non-live provenance.

    Seed entries imported specifically for later live verification are not
    enough to support a cited claim.  Separately supplied authoritative or
    manual sources can be useful, but they still need explicit mixed-provenance
    acceptance before a claim-safe run can be treated as ready.
    """

    origin_tokens = {
        token.strip().lower()
        for token in re.split(r"[+,;]", str(item.get("origin") or ""))
        if token.strip()
    }
    if origin_tokens and origin_tokens <= {"metadata_seed_for_live_verification"}:
        return False
    if origin_tokens & {"operator_authoritative_source", "manual_bibtex", "manual_seed", "codex_web_seed"}:
        return True
    external_ids = item.get("external_ids")
    has_external_ids = isinstance(external_ids, dict) and any(str(value).strip() for value in external_ids.values())
    has_url = bool(str(item.get("url") or "").strip())
    return has_url or has_external_ids


def _citation_registry_live_provenance(
    registry_path: str | Path | None,
    paper_path: str | Path | None = None,
) -> dict[str, Any]:
    empty_fields = {
        "registry_count": 0,
        "live_verified_count": 0,
        "seed_only_count": 0,
        "mock_entry_count": 0,
        "live_coverage_ratio": 0.0,
        "cited_entry_count": 0,
        "unused_registry_count": 0,
        "cited_live_verified_count": 0,
        "cited_mixed_count": 0,
        "cited_curated_seed_count": 0,
        "cited_mock_count": 0,
    }
    if not registry_path:
        return {**empty_fields, "status": "missing"}
    candidate = Path(registry_path)
    if not candidate.exists():
        return {**empty_fields, "status": "missing"}
    try:
        payload = read_json(candidate)
    except Exception:
        return {**empty_fields, "status": "unreadable"}
    if not isinstance(payload, list):
        return {**empty_fields, "status": "malformed"}
    entries = [item for item in payload if isinstance(item, dict)]
    registry_count = len(entries)
    live_verified_count = sum(1 for item in entries if _registry_entry_has_live_verification(item))
    mock_entry_count = sum(1 for item in entries if _registry_entry_is_mock(item))
    seed_only_count = max(registry_count - live_verified_count - mock_entry_count, 0)
    live_coverage_ratio = (live_verified_count / registry_count) if registry_count else 0.0
    cited_keys: set[str] | None = None
    if paper_path:
        paper = Path(paper_path)
        if paper.exists():
            cited_keys = extract_citation_keys(paper.read_text(encoding="utf-8", errors="replace"))
    if cited_keys is None:
        cited_entries = entries
    else:
        cited_entries = [item for item in entries if _registry_entry_key_aliases(item) & cited_keys]
    cited_entry_count = len(cited_entries)
    cited_live_verified_count = sum(1 for item in cited_entries if _registry_entry_has_live_verification(item))
    cited_mock_count = sum(1 for item in cited_entries if _registry_entry_is_mock(item))
    cited_mixed_count = sum(
        1
        for item in cited_entries
        if not _registry_entry_has_live_verification(item)
        and not _registry_entry_is_mock(item)
        and _registry_entry_has_mixed_non_live_provenance(item)
    )
    cited_curated_seed_count = max(
        cited_entry_count - cited_live_verified_count - cited_mock_count - cited_mixed_count,
        0,
    )
    unused_registry_count = max(registry_count - cited_entry_count, 0)
    cited_scope_active = cited_keys is not None
    if not registry_count:
        status = "empty"
    elif cited_mock_count:
        status = "mock"
    elif cited_mixed_count:
        status = "mixed"
    elif cited_curated_seed_count:
        status = "curated"
    elif cited_scope_active:
        status = "live"
    elif mock_entry_count:
        status = "mock"
    elif seed_only_count:
        status = "mixed"
    else:
        status = "live"
    return {
        "registry_count": registry_count,
        "live_verified_count": live_verified_count,
        "seed_only_count": seed_only_count,
        "mock_entry_count": mock_entry_count,
        "live_coverage_ratio": live_coverage_ratio,
        "cited_entry_count": cited_entry_count,
        "unused_registry_count": unused_registry_count,
        "cited_live_verified_count": cited_live_verified_count,
        "cited_mixed_count": cited_mixed_count,
        "cited_curated_seed_count": cited_curated_seed_count,
        "cited_mock_count": cited_mock_count,
        "status": status,
    }
