from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contract import _read_packet
from paperorchestra.feedback.operator_contexts.packet import _packet_payload_by_role
from paperorchestra.feedback.operator_contexts.text import _normalized_context_text, _truncate_context_text


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

def _protected_citation_target_context(
    citation_review_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, set[str]]:
    """Return exact citation-repair targets that should not be protected.

    Weak/problematic citation support is placement-specific, especially for v3
    source-backed cases where one bibkey can support one anchor and fail
    another.  Therefore weak support contributes exact ids/texts only.  By
    contrast duplicate-support and citation-density repairs legitimately target
    any repeated/dense use of an affected key, so those contribute key-level
    exclusions.
    """

    problematic_statuses = {
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
    ids: set[str] = set()
    texts: set[str] = set()
    key_exclusions: set[str] = set()
    if isinstance(citation_review_payload, dict):
        for item in citation_review_payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("support_status") or item.get("status") or "").strip()
            if status not in problematic_statuses:
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
            if verdict not in problematic_statuses:
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

def _protected_supported_citation_regressions(
    imported: dict[str, Any],
    candidate_text: str,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    packet_path = imported.get("packet_path")
    if not packet_path:
        return []
    try:
        packet = _read_packet(packet_path)
    except Exception:
        return []
    citation_review = _packet_payload_by_role(packet, "citation_support_review")
    citation_integrity_audit = _packet_payload_by_role(packet, "citation_integrity_audit")
    protected = _protected_supported_citation_context(
        citation_review,
        citation_integrity_audit,
        limit=10_000,
    )
    if not isinstance(protected, list) or not protected:
        return []
    normalized_candidate = _normalized_context_text(candidate_text)
    regressions: list[dict[str, Any]] = []
    for item in protected:
        if not isinstance(item, dict):
            continue
        text = _protected_item_text(item)
        if not text or text in normalized_candidate:
            continue
        compact = {
            "id": str(item.get("id") or ""),
            "citation_keys": [str(key) for key in item.get("citation_keys") or [] if str(key).strip()],
        }
        if item.get("source_shape"):
            compact["source_shape"] = str(item.get("source_shape"))
        regressions.append(compact)
        if len(regressions) >= limit:
            break
    return regressions

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
