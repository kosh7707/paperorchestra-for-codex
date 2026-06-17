from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text


def _truncate_context_text(value: Any, *, limit: int = 800) -> str:
    text = sanitize_author_facing_text(value, fallback="")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"

def _normalized_context_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
