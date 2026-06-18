from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.citation_protection_supported_shapes import (
    _protected_item_text,
    _supported_case_context,
    _supported_item_context,
)
from paperorchestra.feedback.operator_contexts.citation_protection_target_context import _protected_citation_target_context


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

    for item in citation_review_payload.get("items") or []:
        if isinstance(item, dict):
            context = _supported_item_context(item, targets, ordinal=len(protected) + 1)
            if context:
                protected.append(context)
        if len(protected) >= limit:
            return protected

    for case in citation_review_payload.get("cases") or []:
        if isinstance(case, dict):
            context = _supported_case_context(case, targets, ordinal=len(protected) + 1)
            if context:
                protected.append(context)
        if len(protected) >= limit:
            break
    return protected


__all__ = ["_protected_item_text", "_protected_supported_citation_context"]
