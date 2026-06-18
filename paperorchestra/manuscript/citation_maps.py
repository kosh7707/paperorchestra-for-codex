from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citation_key_parsing import (
    CITE_COMMAND_RE,
    _citation_key_aliases,
    extract_citation_keys,
)


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
        entry = citation_map.get(canonical)
        if entry is None:
            for raw_key, raw_entry in citation_map.items():
                if isinstance(raw_key, str) and canonical_citation_key(raw_key, citation_map) == canonical:
                    entry = raw_entry
                    break
        compact[canonical] = entry if entry is not None else {}
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


def noncanonical_citation_aliases(latex: str, citation_map: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if not isinstance(citation_map, dict):
        return aliases
    for key in extract_citation_keys(latex):
        canonical = canonical_citation_key(key, citation_map)
        if canonical != key:
            aliases[key] = canonical
    return aliases


def canonicalize_citation_keys(latex: str, citation_map: dict[str, Any]) -> tuple[str, dict[str, str]]:
    alias_map: dict[str, str | None] = {}
    for key in citation_map:
        if not isinstance(key, str):
            continue
        canonical_key = canonical_citation_key(key, citation_map)
        for alias in _citation_key_aliases(key):
            lowered = alias.lower()
            if lowered not in alias_map:
                alias_map[lowered] = canonical_key
            elif alias_map[lowered] != canonical_key:
                alias_map[lowered] = None

    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        raw_keys = [part.strip() for part in match.group(2).split(",")]
        updated: list[str] = []
        changed = False
        for raw_key in raw_keys:
            if not raw_key:
                continue
            canonical = canonical_citation_key(raw_key, citation_map) if raw_key in citation_map else None
            if canonical and canonical != raw_key:
                replacements[raw_key] = canonical
                updated.append(canonical)
                changed = True
                continue
            if raw_key in citation_map:
                updated.append(raw_key)
                continue
            canonical = alias_map.get(raw_key.lower())
            if canonical and canonical not in {None, ""}:
                replacements[raw_key] = canonical
                updated.append(canonical)
                changed = True
            else:
                updated.append(raw_key)
        if not changed:
            return match.group(0)
        return match.group(1) + "{" + ", ".join(updated) + "}"

    return CITE_COMMAND_RE.sub(_replace, latex), replacements
