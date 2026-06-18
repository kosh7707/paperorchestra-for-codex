from __future__ import annotations

import re
from typing import Any

UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _fields_present(item: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if str(item.get("title") or "").strip():
        fields.append("title")
    if item.get("authors"):
        fields.append("author")
    if item.get("year") is not None:
        fields.append("year")
    if str(item.get("venue") or "").strip():
        fields.append("venue")
    if str(item.get("url") or "").strip():
        fields.append("url")
    external = item.get("external_ids") if isinstance(item.get("external_ids"), dict) else {}
    if external:
        fields.append("external_ids")
    return fields


def _unknown_fields(item: dict[str, Any]) -> list[str]:
    unknown: list[str] = []
    if _unknown_value(str(item.get("title") or "")):
        unknown.append("title")
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    if not authors or all(_unknown_value(str(author)) for author in authors):
        unknown.append("author")
    if item.get("year") is None:
        unknown.append("year")
    return unknown


def _unknown_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return normalized in UNKNOWN_VALUES
