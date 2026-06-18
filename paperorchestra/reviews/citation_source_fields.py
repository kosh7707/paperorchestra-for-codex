from __future__ import annotations

from typing import Any


def _clean_optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
