from __future__ import annotations

import re
from typing import Any


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
