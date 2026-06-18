from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.citations import CITE_COMMAND_RE
from paperorchestra.reviews.source_support_terms import _meaningful_term_sequence


def _cited_key_terms(case: dict[str, Any]) -> set[str]:
    keys = {str(case.get("key") or "")}
    for match in CITE_COMMAND_RE.finditer(str(case.get("anchor") or "")):
        keys.update(item.strip() for item in match.group(2).split(",") if item.strip())
    return {term for key in keys for term in _meaningful_term_sequence(key)}


def _target_subject_terms(case: dict[str, Any], target_terms: set[str]) -> set[str]:
    key_terms = set(_meaningful_term_sequence(str(case.get("key") or "")))
    subject = key_terms & target_terms
    if subject:
        return subject
    sequence = _meaningful_term_sequence(str(case.get("target") or ""))
    return {sequence[0]} if sequence else set()
