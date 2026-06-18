from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.citation_protection_targets import _protected_citation_target_context
from paperorchestra.feedback.operator_contexts.text import _normalized_context_text


def _protected_supported_citation_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    if not isinstance(citation_review_payload, dict):
        return []
    targets = _protected_citation_target_context(citation_review_payload, citation_integrity_payload)
    protected: list[dict[str, Any]] = []

    def _is_excluded(entry_id: str, text: str, keys: list[str]) -> bool:
        if entry_id and entry_id in targets["ids"]:
            return True
        normalized = _normalized_context_text(text)
        if normalized and normalized in targets["texts"]:
            return True
        return bool(set(keys) & targets["key_exclusions"])

    for item in citation_review_payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or item.get("status") or "").strip()
        if status != "supported":
            continue
        sentence = _normalized_context_text(item.get("sentence"))
        keys = [str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip()]
        entry_id = str(item.get("id") or "").strip()
        if not sentence or _is_excluded(entry_id, sentence, keys):
            continue
        protected.append(
            {
                "id": entry_id or f"supported-item-{len(protected) + 1}",
                "citation_keys": keys,
                "sentence": sentence,
                "source_shape": "items",
                "required_action": "preserve this already-supported citation-bearing sentence unless an active issue explicitly targets it",
            }
        )
        if len(protected) >= limit:
            return protected

    for case in citation_review_payload.get("cases") or []:
        if not isinstance(case, dict):
            continue
        verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
        if verdict not in {"pass", "supported"}:
            continue
        anchor = _normalized_context_text(case.get("anchor") or case.get("target"))
        keys = [str(case.get("key")).strip()] if str(case.get("key") or "").strip() else []
        entry_id = str(case.get("id") or "").strip()
        if not anchor or _is_excluded(entry_id, anchor, keys):
            continue
        protected.append(
            {
                "id": entry_id or f"supported-case-{len(protected) + 1}",
                "citation_keys": keys,
                "anchor": anchor,
                "source_shape": "cases",
                "required_action": "preserve this already-supported citation-bearing anchor unless an active issue explicitly targets it",
            }
        )
        if len(protected) >= limit:
            break
    return protected


def _protected_item_text(item: dict[str, Any]) -> str:
    return _normalized_context_text(item.get("sentence") or item.get("anchor"))
