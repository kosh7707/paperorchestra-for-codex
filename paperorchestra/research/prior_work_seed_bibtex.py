from __future__ import annotations

import re
from typing import Any

from paperorchestra.research.prior_work_seed_normalization import _normalize_seed_entry

_BIBTEX_SEED_FIELDS = ["title", "author", "editor", "organization", "year", "journal", "booktitle", "venue", "url", "doi", "abstract"]


def _extract_bibtex_field(body: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*", body, re.IGNORECASE)
    if not match:
        return None
    idx = match.end()
    while idx < len(body) and body[idx].isspace():
        idx += 1
    if idx >= len(body):
        return None
    opener = body[idx]
    if opener == "{":
        return _extract_braced_bibtex_value(body, idx)
    if opener == '"':
        return _extract_quoted_bibtex_value(body, idx)
    bare_match = re.match(r"([^,\n]+)", body[idx:])
    return bare_match.group(1).strip() if bare_match else None


def _extract_braced_bibtex_value(body: str, opener_index: int) -> str | None:
    depth = 0
    start = opener_index + 1
    idx = start
    while idx < len(body):
        ch = body[idx]
        if ch == "{" and body[idx - 1] != "\\":
            depth += 1
        elif ch == "}" and body[idx - 1] != "\\":
            if depth == 0:
                return re.sub(r"\s+", " ", body[start:idx]).strip()
            depth -= 1
        idx += 1
    return None


def _extract_quoted_bibtex_value(body: str, opener_index: int) -> str | None:
    start = opener_index + 1
    idx = start
    while idx < len(body):
        if body[idx] == '"' and body[idx - 1] != "\\":
            return re.sub(r"\s+", " ", body[start:idx]).strip()
        idx += 1
    return None


def _parse_bibtex_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"@\w+\s*\{\s*([^,]+)\s*,(.*?)(?=\n@\w+\s*\{|\Z)", text, re.DOTALL):
        key = match.group(1).strip()
        body = match.group(2)
        fields: dict[str, str] = {"source": default_source, "provenance_note": f"Imported from BibTeX key {key}.", "bibtex_key": key}
        for field in _BIBTEX_SEED_FIELDS:
            value = _extract_bibtex_field(body, field)
            if value:
                fields[field] = value
        normalized = _normalize_seed_entry(fields, default_source=default_source)
        if normalized:
            entries.append(normalized)
    return entries
