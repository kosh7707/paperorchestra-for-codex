from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.text import _normalized_context_text

_PROBLEMATIC_STATUSES = {
    "weakly_supported",
    "unsupported",
    "contradicted",
    "insufficient_evidence",
    "needs_manual_check",
    "manual_check",
    "metadata_only",
    "evidence_missing",
    "weak",
    "fail",
    "human_needed",
}


def _protected_citation_target_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, set[str]]:
    """Return exact citation-repair targets that should not be protected."""

    ids: set[str] = set()
    texts: set[str] = set()
    key_exclusions: set[str] = set()
    if isinstance(citation_review_payload, dict):
        for item in citation_review_payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("support_status") or item.get("status") or "").strip()
            if status not in _PROBLEMATIC_STATUSES:
                continue
            item_id = str(item.get("id") or "").strip()
            if item_id:
                ids.add(item_id)
            sentence = _normalized_context_text(item.get("sentence"))
            if sentence:
                texts.add(sentence)
        for case in citation_review_payload.get("cases") or []:
            if not isinstance(case, dict):
                continue
            verdict = str(case.get("verdict") or case.get("support_status") or case.get("status") or "").strip()
            if verdict not in _PROBLEMATIC_STATUSES:
                continue
            case_id = str(case.get("id") or "").strip()
            if case_id:
                ids.add(case_id)
            text = _normalized_context_text(case.get("anchor") or case.get("target"))
            if text:
                texts.add(text)

    checks = citation_integrity_payload.get("checks") if isinstance(citation_integrity_payload, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    key_exclusions.update(str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip())
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        key_exclusions.update(str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip())
        sentence = _normalized_context_text(item.get("sentence"))
        if sentence:
            texts.add(sentence)
    for key_set in density.get("bomb_paragraph_key_sets") or []:
        if isinstance(key_set, list):
            key_exclusions.update(str(key).strip() for key in key_set if str(key).strip())
    return {"ids": ids, "texts": texts, "key_exclusions": key_exclusions}
