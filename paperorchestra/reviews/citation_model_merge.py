from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_evidence import (
    _clean_evidence,
    _normalize_risk,
    _normalize_support_status,
    _valid_cited_source_evidence,
)


def _merge_model_citation_review(
    heuristic_items: list[dict[str, Any]],
    model_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    by_id = {str(item.get("id")): item for item in model_payload.get("items", []) if isinstance(item, dict)}
    merged: list[dict[str, Any]] = []
    for item in heuristic_items:
        model_item = by_id.get(item["id"])
        next_item = dict(item)
        if model_item is None:
            next_item.update(
                {
                    "support_status": "needs_manual_check",
                    "risk": "medium",
                    "model_reasoning": "Model citation-support review omitted this claim.",
                    "suggested_fix": "Manually verify this cited sentence or rerun the citation-support critic.",
                }
            )
        else:
            status = _normalize_support_status(model_item.get("support_status"))
            evidence = _clean_evidence(model_item.get("evidence"))
            candidate_item = dict(next_item)
            candidate_item["evidence"] = evidence
            valid_supporting_evidence = _valid_cited_source_evidence(evidence, candidate_item)
            if status == "supported" and not valid_supporting_evidence:
                status = "needs_manual_check"
            next_item.update(
                {
                    "support_status": status,
                    "risk": _normalize_risk(model_item.get("risk"), status),
                    "claim_type": str(model_item.get("claim_type") or next_item.get("claim_type") or "background"),
                    "evidence": evidence,
                    "critic_source": "model",
                    "evidence_strength": "model_supporting_evidence"
                    if status == "supported" and valid_supporting_evidence
                    else "insufficient_model_evidence"
                    if evidence
                    else "none",
                    "model_reasoning": str(model_item.get("reasoning") or "").strip(),
                    "suggested_fix": str(model_item.get("suggested_fix") or next_item.get("suggested_fix") or "").strip(),
                }
            )
        merged.append(next_item)
    return merged
