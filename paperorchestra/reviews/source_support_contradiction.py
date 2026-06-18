from __future__ import annotations

from paperorchestra.reviews.source_support_terms import _meaningful_terms

_CONTRADICTION_MARKERS = (
    "does not",
    "do not",
    "did not",
    "is not",
    "are not",
    "not use",
    "not uses",
    "without",
    "no evidence",
    "fails to",
    "unrelated to",
    "contradicts",
)


def _window_has_in_scope_contradiction(window: str, subject_terms: set[str], relation_terms: set[str]) -> bool:
    terms = _meaningful_terms(window)
    if subject_terms and not (subject_terms & terms):
        return False
    if len(relation_terms & terms) < min(2, len(relation_terms)):
        return False
    lower = window.lower().replace("not only", "").replace("not merely", "")
    return any(marker in lower for marker in _CONTRADICTION_MARKERS)
