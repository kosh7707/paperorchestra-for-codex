from __future__ import annotations

import re
from typing import Any


def _coerce_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            return int(match.group(0))
    return None


def _entry_year_with_source(entry: dict[str, Any]) -> tuple[int | None, str | None]:
    for key in ("year", "publication_year", "date"):
        year = _coerce_year(entry.get(key))
        if year is not None:
            return year, key
    return None, None
