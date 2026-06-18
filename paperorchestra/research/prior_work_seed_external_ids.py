from __future__ import annotations

import re
from typing import Any


def _normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\b(10\.\d{4,9}/[^\s,;{}]+)", value)
    if not match:
        return None
    return match.group(1).rstrip(").,;")


def _entry_external_ids(entry: dict[str, Any]) -> dict[str, str]:
    external = entry.get("externalIds") or entry.get("external_ids") or {}
    result = {str(k): str(v) for k, v in external.items()} if isinstance(external, dict) else {}
    doi = entry.get("doi") or entry.get("DOI")
    normalized_doi = _normalize_doi(doi) if isinstance(doi, str) else None
    if normalized_doi:
        result["DOI"] = normalized_doi
    arxiv = entry.get("arxiv") or entry.get("ArXiv")
    if isinstance(arxiv, str) and arxiv.strip():
        result["ArXiv"] = arxiv.strip()
    return result
