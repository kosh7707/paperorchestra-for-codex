from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.citations import canonical_citation_key
from paperorchestra.reviews import reproducibility_payloads as _payloads


def _bibtex_keys_from_text(text: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)", text))


def _registry_surface_health(registry_exists: bool, registry_payload: Any) -> tuple[list[str], int, set[str], set[str]]:
    if not registry_exists:
        return [], 0, set(), set()
    if not isinstance(registry_payload, list):
        return ["citation_registry.json is unreadable or malformed."], 0, set(), set()

    invalid = 0
    registry_keys: set[str] = set()
    registry_alias_keys: set[str] = set()
    for item in registry_payload:
        if not _payloads._is_valid_verified_paper_payload(item):
            invalid += 1
            continue
        key = item.get("bibtex_key")
        aliases = item.get("alias_bibtex_keys") or []
        if isinstance(key, str) and key.strip():
            registry_keys.add(key.strip())
        registry_alias_keys.update(alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip())
    valid = len(registry_payload) - invalid
    if valid == 0 and invalid == 0:
        return ["citation_registry.json is empty."], 0, registry_keys, registry_alias_keys
    if invalid > 0:
        return [f"citation_registry.json contains malformed entries ({invalid} invalid)."], valid, registry_keys, registry_alias_keys
    return [], valid, registry_keys, registry_alias_keys


def _citation_map_surface_health(citation_map_exists: bool, citation_map_payload: Any) -> tuple[list[str], int, set[str], set[str]]:
    if not citation_map_exists:
        return [], 0, set(), set()
    if not isinstance(citation_map_payload, dict):
        return ["citation_map.json is unreadable or malformed."], 0, set(), set()

    invalid = 0
    citation_map_keys: set[str] = set()
    citation_map_canonical_keys: set[str] = set()
    for key, entry in citation_map_payload.items():
        if not _payloads._is_valid_citation_map_entry(key, entry):
            invalid += 1
            continue
        citation_map_keys.add(key.strip())
        citation_map_canonical_keys.add(canonical_citation_key(key.strip(), citation_map_payload))
    valid = len(citation_map_payload) - invalid
    if valid == 0 and invalid == 0:
        return ["citation_map.json is empty."], 0, citation_map_keys, citation_map_canonical_keys
    if invalid > 0:
        return [f"citation_map.json contains malformed entries ({invalid} invalid)."], valid, citation_map_keys, citation_map_canonical_keys
    return [], valid, citation_map_keys, citation_map_canonical_keys


def _references_bib_surface_health(
    references_bib_path: str | Path | None,
    references_bib_exists: bool,
) -> tuple[list[str], int, set[str]]:
    if not references_bib_exists:
        return [], 0, set()
    bib_candidate = Path(references_bib_path)
    if not bib_candidate.is_file():
        return ["references.bib is unreadable or malformed."], 0, set()
    try:
        bib_text = bib_candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["references.bib is unreadable or malformed."], 0, set()

    entry_count = len(re.findall(r"(?m)^\s*@[A-Za-z]+(?:\s*|\{)", bib_text))
    bib_keys = _bibtex_keys_from_text(bib_text)
    if entry_count == 0:
        return ["references.bib is empty."], entry_count, bib_keys
    if not bib_keys:
        return ["references.bib contains BibTeX entries without extractable keys."], entry_count, bib_keys
    return [], entry_count, bib_keys
