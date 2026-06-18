from __future__ import annotations

import re
from typing import Any


def _split_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return _authors_from_list(value)
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"\s+and\s+|;\s*|,\s*(?=[A-Z][A-Za-z]+(?:\s|$))", value) if item.strip()]
    return []


def _authors_from_list(value: list[Any]) -> list[str]:
    result = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result.append(item["name"].strip())
        elif isinstance(item, str):
            result.append(item.strip())
    return [item for item in result if item]
