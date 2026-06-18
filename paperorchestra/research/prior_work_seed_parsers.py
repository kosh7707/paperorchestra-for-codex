from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.research.prior_work_seed_authors import _split_authors
from paperorchestra.research.prior_work_seed_dates import _coerce_year
from paperorchestra.research.prior_work_seed_entry import _normalize_seed_entry
from paperorchestra.research.prior_work_seed_external_ids import _entry_external_ids, _normalize_doi

_BIBTEX_SEED_FIELDS = ["title", "author", "editor", "organization", "year", "journal", "booktitle", "venue", "url", "doi", "abstract"]


def _parse_json_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = payload.get("references") or payload.get("papers") or payload.get("prior_work") or payload.get("entries") or []
    else:
        raw_entries = []
    result: list[dict[str, Any]] = []
    for item in raw_entries:
        if isinstance(item, dict):
            normalized = _normalize_seed_entry(item, default_source=default_source)
            if normalized:
                result.append(normalized)
    return result


def _parse_markdown_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        item = stripped.lstrip("-* ").strip()
        if not item:
            continue
        title, url = _markdown_seed_title_and_url(item)
        if len(title) < 4:
            continue
        year = _coerce_year(item)
        entries.append(
            {
                "title": title,
                "authors": [],
                "year": year,
                "publication_date": f"{year}-01-01" if year else None,
                "venue": None,
                "abstract": f"Curated prior-work seed imported from markdown line: {item}",
                "citation_count": None,
                "external_ids": _entry_external_ids({"doi": _normalize_doi(item)}),
                "url": url,
                "source": default_source,
                "provenance_notes": [item],
            }
        )
    return entries


def _markdown_seed_title_and_url(item: str) -> tuple[str, str | None]:
    link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", item)
    if link_match:
        title = link_match.group(1).strip()
        url = link_match.group(2).strip()
    else:
        title = re.split(r"\s+[—–-]\s+|\s+\|\s+", item, maxsplit=1)[0].strip()
        url = None
    return re.sub(r"^\d+\.\s*", "", title).strip(" ."), url


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


def load_prior_work_seed(path: str | Path, *, source: str = "manual_seed") -> list[dict[str, Any]]:
    seed_path = Path(path)
    text = seed_path.read_text(encoding="utf-8")
    suffix = seed_path.suffix.lower()
    if suffix == ".json":
        return _parse_json_seed(text, default_source=source)
    if suffix in {".bib", ".bibtex"} or text.lstrip().startswith("@"):
        return _parse_bibtex_seed(text, default_source=source)
    return _parse_markdown_seed(text, default_source=source)
