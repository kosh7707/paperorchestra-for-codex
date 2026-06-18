from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.citation_protection_statuses import _PROBLEMATIC_STATUSES
from paperorchestra.feedback.operator_contexts.text import _normalized_context_text


def _review_problem_targets(citation_review_payload: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    texts: set[str] = set()
    if not isinstance(citation_review_payload, dict):
        return ids, texts
    for item in citation_review_payload.get("items") or []:
        _add_review_item_target(item, ids=ids, texts=texts)
    for case in citation_review_payload.get("cases") or []:
        _add_review_case_target(case, ids=ids, texts=texts)
    return ids, texts


def _add_review_item_target(item: Any, *, ids: set[str], texts: set[str]) -> None:
    if not isinstance(item, dict):
        return
    status = str(item.get("support_status") or item.get("status") or "").strip()
    if status not in _PROBLEMATIC_STATUSES:
        return
    item_id = str(item.get("id") or "").strip()
    if item_id:
        ids.add(item_id)
    sentence = _normalized_context_text(item.get("sentence"))
    if sentence:
        texts.add(sentence)


def _add_review_case_target(case: Any, *, ids: set[str], texts: set[str]) -> None:
    if not isinstance(case, dict):
        return
    verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
    if verdict not in _PROBLEMATIC_STATUSES:
        return
    case_id = str(case.get("id") or "").strip()
    if case_id:
        ids.add(case_id)
    text = _normalized_context_text(case.get("anchor") or case.get("target"))
    if text:
        texts.add(text)
