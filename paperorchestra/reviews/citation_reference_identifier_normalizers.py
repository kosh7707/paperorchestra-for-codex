from __future__ import annotations

import re
from typing import Any

from paperorchestra.reviews.citation_reference_unknowns import _is_unknown_value


def _normalize_doi(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    return text.strip(" .;,").lower() or None


def _normalize_eprint(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^arxiv:", "", text, flags=re.IGNORECASE)
    return text.lower().strip(" .;,") or None


def _standard_identity_from_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    match = re.search(r"\b(rfc)\s*-?\s*(\d{3,5})\b", text, flags=re.IGNORECASE)
    if match:
        return f"standard:{match.group(1).lower()}-{match.group(2)}"
    return None
