from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import normalized_coverage_groups
from paperorchestra.manuscript.claim_coverage import _terms_nearby


def _narrative_terms_from_item(item: Any) -> list[str]:
    if isinstance(item, dict):
        groups = normalized_coverage_groups(item)
        terms = [term for group in groups for term in group]
        if terms:
            return terms[:8]
        text = str(item.get("authorial_claim") or item.get("beat") or item.get("text") or "")
    else:
        text = str(item)
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", text)[:6]


def _narrative_item_covered(section_text: str, item: Any) -> bool:
    if isinstance(item, dict) and item.get("coverage_groups"):
        for group in normalized_coverage_groups(item):
            terms = [str(term) for term in group if str(term).strip()]
            if terms and _terms_nearby(section_text, terms):
                return True
        return False
    terms = _narrative_terms_from_item(item)
    return not terms or any(term.lower() in section_text.lower() for term in terms)
