from __future__ import annotations

import re
from typing import Any

from paperorchestra.reviews.citation_reference_unknowns import _is_unknown_value

_REPORT_NAMESPACE_FIELDS = ("organization", "institution", "venue", "journal", "booktitle", "series", "publisher", "school")


def _normalize_report_number(value: Any) -> str | None:
    text = re.sub(r"\s+", "-", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    if not text or _is_unknown_value(text):
        return None
    return text


def _namespace_for_report(entry: dict[str, Any]) -> str | None:
    values = [
        str(entry.get(field) or "").strip().lower()
        for field in _REPORT_NAMESPACE_FIELDS
        if not _is_unknown_value(str(entry.get(field) or ""))
    ]
    if not values:
        return None
    namespace = re.sub(r"\s+", "-", values[0])
    namespace = re.sub(r"[^a-z0-9._-]+", "-", namespace).strip("-._")
    return namespace or None
