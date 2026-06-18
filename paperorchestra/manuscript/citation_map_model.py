from __future__ import annotations

from typing import Any


def canonical_citation_key(key: str, citation_map: dict[str, Any]) -> str:
    entry = citation_map.get(key) if isinstance(citation_map, dict) else None
    if isinstance(entry, dict):
        canonical = entry.get("canonical_bibtex_key")
        if isinstance(canonical, str) and canonical.strip():
            return canonical.strip()
    return key


def canonical_citation_keys(citation_map: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if not isinstance(citation_map, dict):
        return result
    for raw_key in citation_map:
        if not isinstance(raw_key, str) or not raw_key.strip():
            continue
        canonical = canonical_citation_key(raw_key, citation_map)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def canonical_citation_map(citation_map: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    if not isinstance(citation_map, dict):
        return compact
    for canonical in canonical_citation_keys(citation_map):
        compact[canonical] = _entry_for_canonical_key(citation_map, canonical)
    return compact


def allowed_citation_keys(citation_map: dict[str, Any]) -> set[str]:
    if not isinstance(citation_map, dict):
        return set()
    raw_keys = {key for key in citation_map if isinstance(key, str) and key.strip()}
    return raw_keys | set(canonical_citation_keys(citation_map))


def citation_entry_for_key(citation_map: dict[str, Any], key: str) -> dict[str, Any]:
    if not isinstance(citation_map, dict):
        return {}
    raw = citation_map.get(key)
    if isinstance(raw, dict):
        return raw
    canonical_entry = canonical_citation_map(citation_map).get(key)
    return canonical_entry if isinstance(canonical_entry, dict) else {}


def _entry_for_canonical_key(citation_map: dict[str, Any], canonical: str) -> Any:
    entry = citation_map.get(canonical)
    if entry is not None:
        return entry
    for raw_key, raw_entry in citation_map.items():
        if isinstance(raw_key, str) and canonical_citation_key(raw_key, citation_map) == canonical:
            return raw_entry
    return {}
