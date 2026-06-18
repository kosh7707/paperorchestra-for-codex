from __future__ import annotations

from typing import Any


def _truncate_issue_text(value: Any, *, limit: int = 900) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
