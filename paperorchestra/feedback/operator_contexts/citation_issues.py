from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _truncate_context_text


def _problematic_citation_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    problematic_statuses = {
        "weakly_supported",
        "unsupported",
        "contradicted",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "metadata_only",
        "evidence_missing",
    }
    result: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("support_status") or item.get("status") or "").strip()
        if status not in problematic_statuses:
            continue
        result.append(
            {
                "id": item.get("id"),
                "support_status": status,
                "claim_type": item.get("claim_type"),
                "risk": item.get("risk"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "citation_keys": [str(key) for key in item.get("citation_keys") or []],
                "suggested_fix": _truncate_context_text(item.get("suggested_fix"), limit=500),
                "model_reasoning": _truncate_context_text(item.get("model_reasoning"), limit=700),
            }
        )
        if len(result) >= limit:
            break
    return result


def _duplicate_support_context(
    citation_integrity_payload: dict[str, Any] | None,
    citation_review_payload: dict[str, Any] | None,
    *,
    limit: int = 16,
    examples_per_key: int = 4,
) -> list[dict[str, Any]]:
    if not isinstance(citation_integrity_payload, dict):
        return []
    checks = citation_integrity_payload.get("checks") if isinstance(citation_integrity_payload.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    duplicate_keys = [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]
    if not duplicate_keys:
        return []
    review_items = citation_review_payload.get("items") if isinstance(citation_review_payload, dict) else []
    support_items = [item for item in review_items if isinstance(item, dict)] if isinstance(review_items, list) else []
    result: list[dict[str, Any]] = []
    for key in duplicate_keys:
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
        result.append(
            {
                "issue_type": "citation_duplicate_support",
                "citation_key": key,
                "occurrence_count": len(affected) or None,
                "affected_items": affected[:examples_per_key],
                "suggested_fix": (
                    "Keep this citation only where it directly supports a distinct claim; "
                    "otherwise remove the repeated key, merge redundant support, or redistribute existing citations without adding bibliography keys."
                ),
            }
        )
        if len(result) >= limit:
            break
    return result


def _citation_density_context(payload: dict[str, Any] | None, *, limit: int = 16) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    result: list[dict[str, Any]] = []
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        keys = [str(key) for key in item.get("citation_keys") or [] if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_sentence",
                "id": item.get("id"),
                "sentence": _truncate_context_text(item.get("sentence"), limit=900),
                "citation_keys": keys,
                "citation_count": len(keys),
                "suggested_fix": "Split the sentence, remove redundant references, or scope the claim while preserving directly supporting citations.",
            }
        )
        if len(result) >= limit:
            return result
    for index, keys in enumerate(density.get("bomb_paragraph_key_sets") or [], start=1):
        if not isinstance(keys, list):
            continue
        normalized = [str(key) for key in keys if str(key).strip()]
        result.append(
            {
                "issue_type": "citation_bomb_paragraph",
                "id": f"citation-bomb-paragraph-{index}",
                "citation_keys": normalized,
                "citation_count": len(normalized),
                "suggested_fix": "Distribute citations across claim-specific sentences or remove redundant references.",
            }
        )
        if len(result) >= limit:
            break
    return result
