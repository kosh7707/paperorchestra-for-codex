from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _duplicate_support_context(
    citation_integrity_payload: dict[str, Any] | None,
    citation_review_payload: dict[str, Any] | None,
    *,
    limit: int = 16,
    examples_per_key: int = 4,
) -> list[dict[str, Any]]:
    duplicate_keys = _duplicate_support_keys(citation_integrity_payload)
    if not duplicate_keys:
        return []
    support_items = _support_items(citation_review_payload)
    result: list[dict[str, Any]] = []
    for key in duplicate_keys:
        affected = _affected_support_items(key, support_items)
        result.append(_duplicate_support_issue(key, affected, examples_per_key=examples_per_key))
        if len(result) >= limit:
            break
    return result


def _duplicate_support_keys(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    return [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]


def _support_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    review_items = payload.get("items") if isinstance(payload, dict) else []
    return [item for item in review_items if isinstance(item, dict)] if isinstance(review_items, list) else []


def _affected_support_items(key: str, support_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    for index, item in enumerate(support_items, start=1):
        keys = {str(candidate).strip() for candidate in item.get("citation_keys") or [] if str(candidate).strip()}
        if key not in keys:
            continue
        affected.append(
            {
                "id": str(item.get("id") or f"citation-support-{index}"),
                "support_status": str(item.get("support_status") or item.get("status") or "unknown"),
                "claim_type": item.get("claim_type"),
                "risk": item.get("risk"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
            }
        )
    return affected


def _duplicate_support_issue(
    key: str,
    affected: list[dict[str, Any]],
    *,
    examples_per_key: int,
) -> dict[str, Any]:
    return {
        "issue_type": "citation_duplicate_support",
        "citation_key": key,
        "occurrence_count": len(affected) or None,
        "affected_items": affected[:examples_per_key],
        "suggested_fix": (
            "Keep this citation only where it directly supports a distinct claim; "
            "otherwise remove the repeated key, merge redundant support, or redistribute existing citations without adding bibliography keys."
        ),
    }
