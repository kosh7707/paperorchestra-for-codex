from __future__ import annotations

import math
from typing import Any

from paperorchestra.reviews.source_support_case_terms import _cited_key_terms, _target_subject_terms
from paperorchestra.reviews.source_support_contradiction import _window_has_in_scope_contradiction
from paperorchestra.reviews.source_support_terms import _meaningful_terms, _source_text_windows


def _classify_source_support(case: dict[str, Any], source_text: str) -> tuple[str, str]:
    target_terms = _meaningful_terms(str(case.get("target") or ""))
    if not target_terms:
        return "weak", "The retrieved source artifact is available, but the target claim could not be isolated."
    subject_terms = _target_subject_terms(case, target_terms)
    cited_key_terms = _cited_key_terms(case)
    relation_terms = set(target_terms) - subject_terms - cited_key_terms
    threshold = _relation_pass_threshold(relation_terms)
    best_overlap = 0
    pass_found = False
    for window in _source_text_windows(source_text):
        window_terms = _meaningful_terms(window)
        relation_overlap = len(relation_terms & window_terms)
        best_overlap = max(best_overlap, relation_overlap)
        if _window_has_in_scope_contradiction(window, subject_terms, relation_terms):
            return "fail", "The retrieved source artifact appears to contradict the target claim."
        has_subject = bool(subject_terms & window_terms) if subject_terms else True
        if has_subject and relation_overlap >= threshold:
            pass_found = True
    if pass_found:
        return "pass", "The retrieved source artifact locally supports the target claim."
    if best_overlap or (_meaningful_terms(source_text) & target_terms):
        return "weak", "The retrieved source artifact is related, but local support for the target claim is partial."
    return "weak", "A source artifact was available, but local support for the target claim was not found."


def _relation_pass_threshold(relation_terms: set[str]) -> int:
    count = len(relation_terms)
    if count <= 2:
        return count
    return max(2, math.ceil(0.70 * count))
