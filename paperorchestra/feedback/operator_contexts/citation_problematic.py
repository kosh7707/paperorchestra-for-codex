from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _problematic_citation_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or item.get("status") or "").strip()
        if status not in _PROBLEMATIC_CITATION_STATUSES:
            continue
        result.append(_problematic_citation_item(item, status))
        if len(result) >= limit:
            break
    return result


def _problematic_citation_item(item: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "support_status": status,
        "claim_type": item.get("claim_type"),
        "risk": item.get("risk"),
        "sentence": _truncate_context_text(item.get("sentence"), limit=900),
        "citation_keys": [str(key) for key in item.get("citation_keys") or []],
        "suggested_fix": _truncate_context_text(item.get("suggested_fix"), limit=500),
        "model_reasoning": _truncate_context_text(item.get("model_reasoning"), limit=700),
    }


_PROBLEMATIC_CITATION_STATUSES = {
    "weakly_supported",
    "unsupported",
    "contradicted",
    "insufficient_evidence",
    "needs_manual_check",
    "manual_check",
    "metadata_only",
    "evidence_missing",
}
