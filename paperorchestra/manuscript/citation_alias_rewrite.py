from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citation_key_parsing import CITE_COMMAND_RE, _citation_key_aliases, extract_citation_keys
from paperorchestra.manuscript.citation_map_model import canonical_citation_key


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
    alias_map = _citation_alias_map(citation_map)
    replacements: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        updated, changed = _canonicalized_match_keys(match.group(2), citation_map, alias_map, replacements)
        return match.group(0) if not changed else match.group(1) + "{" + ", ".join(updated) + "}"

    return CITE_COMMAND_RE.sub(_replace, latex), replacements


def _citation_alias_map(citation_map: dict[str, Any]) -> dict[str, str | None]:
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
    return alias_map


def _canonicalized_match_keys(
    raw_group: str,
    citation_map: dict[str, Any],
    alias_map: dict[str, str | None],
    replacements: dict[str, str],
) -> tuple[list[str], bool]:
    updated: list[str] = []
    changed = False
    for raw_key in [part.strip() for part in raw_group.split(",")]:
        if not raw_key:
            continue
        canonical = _canonical_for_raw_key(raw_key, citation_map, alias_map)
        if canonical and canonical != raw_key:
            replacements[raw_key] = canonical
            updated.append(canonical)
            changed = True
        else:
            updated.append(raw_key)
    return updated, changed


def _canonical_for_raw_key(raw_key: str, citation_map: dict[str, Any], alias_map: dict[str, str | None]) -> str | None:
    if raw_key in citation_map:
        return canonical_citation_key(raw_key, citation_map)
    canonical = alias_map.get(raw_key.lower())
    return canonical if canonical not in {None, ""} else None
