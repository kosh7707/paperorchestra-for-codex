from __future__ import annotations

import re
from typing import Any

STABLE_REFERENCE_IDENTITY_FIELDS = {
    "doi",
    "url",
    "eprint",
    "archiveprefix",
    "arxiv",
    "pmid",
    "pmcid",
    "isbn",
    "issn",
    "howpublished",
    "number",
    "reportnumber",
}
REFERENCE_IDENTITY_FALLBACK_FIELDS = {
    "journal",
    "booktitle",
    "venue",
    "publisher",
    "institution",
    "organization",
    "school",
    "series",
}


def _is_unknown_value(value: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _entry_unknown_fields(entry: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if _is_unknown_value(str(entry.get("title") or "")):
        fields.append("title")
    if _is_unknown_value(str(entry.get("author") or entry.get("editor") or entry.get("organization") or "")):
        fields.append("author_or_organization")
    if _is_unknown_value(str(entry.get("year") or entry.get("date") or "")):
        fields.append("year_or_date")
    return fields


def _has_known_field(entry: dict[str, Any], fields: set[str]) -> bool:
    for field in fields:
        value = entry.get(field)
        if value is not None and not _is_unknown_value(str(value)):
            return True
    return False


def _entry_has_stable_identity(entry: dict[str, Any]) -> bool:
    """Return whether a visible reference has enough identity to be auditable."""

    return _has_known_field(entry, STABLE_REFERENCE_IDENTITY_FIELDS) or _has_known_field(
        entry,
        REFERENCE_IDENTITY_FALLBACK_FIELDS,
    )
