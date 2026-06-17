from __future__ import annotations

import math
import re
from typing import Any

from paperorchestra.manuscript.validator import CITE_COMMAND_RE


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _meaningful_terms(text: str) -> set[str]:
    return set(_meaningful_term_sequence(text))


def _meaningful_term_sequence(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "uses",
        "use",
        "using",
        "for",
        "into",
        "also",
        "show",
        "shows",
        "describe",
        "describes",
        "discuss",
        "discusses",
        "guide",
        "guides",
        "guided",
        "systems",
        "system",
        "model",
        "models",
    }
    terms: list[str] = []
    for raw in re.findall(r"[a-z0-9]{3,}", text.lower()):
        term = raw
        if len(term) > 4 and term.endswith("ies"):
            term = term[:-3] + "y"
        elif len(term) > 3 and term.endswith("s"):
            term = term[:-1]
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _source_text_windows(text: str) -> list[str]:
    windows = [_collapse_ws(part) for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if _collapse_ws(part)]
    return windows or [_collapse_ws(text)]


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


def _relation_pass_threshold(relation_terms: set[str]) -> int:
    count = len(relation_terms)
    if count <= 2:
        return count
    return max(2, math.ceil(0.70 * count))


def _window_has_in_scope_contradiction(window: str, subject_terms: set[str], relation_terms: set[str]) -> bool:
    terms = _meaningful_terms(window)
    if subject_terms and not (subject_terms & terms):
        return False
    if len(relation_terms & terms) < min(2, len(relation_terms)):
        return False
    lower = window.lower()
    lower = lower.replace("not only", "").replace("not merely", "")
    markers = (
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
    return any(marker in lower for marker in markers)


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
