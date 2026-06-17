from __future__ import annotations

from paperorchestra.reviews import citation_model_merge as merge
from paperorchestra.reviews import citation_model_review


def _heuristic_item() -> dict[str, object]:
    return {
        "id": "claim-1",
        "sentence": "Prior work studies alert triage.",
        "citation_keys": ["KeyA"],
        "citation_entries": [{"key": "KeyA", "title": "Alert Triage in Practice"}],
        "claim_type": "background",
        "heuristic_support_status": "metadata_only",
        "heuristic_risk": "medium",
        "suggested_fix": "Add direct evidence.",
    }


def test_citation_model_review_facade_exports_merge_policy() -> None:
    assert citation_model_review._merge_model_citation_review is merge._merge_model_citation_review


def test_merge_model_review_marks_omitted_items_for_manual_check() -> None:
    merged = merge._merge_model_citation_review([_heuristic_item()], {"items": []})

    assert merged[0]["support_status"] == "needs_manual_check"
    assert merged[0]["risk"] == "medium"
    assert merged[0]["model_reasoning"] == "Model citation-support review omitted this claim."
    assert merged[0]["suggested_fix"] == "Manually verify this cited sentence or rerun the citation-support critic."


def test_merge_model_review_downgrades_supported_without_valid_cited_source_evidence() -> None:
    payload = {
        "items": [
            {
                "id": "claim-1",
                "support_status": "supported",
                "risk": "low",
                "claim_type": "numeric",
                "evidence": [
                    {
                        "citation_key": "KeyA",
                        "source_title": "Unrelated Paper",
                        "evidence_quote_or_summary": "mentions alert triage",
                        "supports_claim": True,
                    }
                ],
                "reasoning": "Looks related.",
                "suggested_fix": "",
            }
        ]
    }

    merged = merge._merge_model_citation_review([_heuristic_item()], payload)

    assert merged[0]["support_status"] == "needs_manual_check"
    assert merged[0]["risk"] == "low"
    assert merged[0]["critic_source"] == "model"
    assert merged[0]["evidence_strength"] == "insufficient_model_evidence"
    assert merged[0]["claim_type"] == "numeric"
    assert merged[0]["model_reasoning"] == "Looks related."


def test_merge_model_review_keeps_supported_with_valid_cited_source_evidence() -> None:
    payload = {
        "items": [
            {
                "id": "claim-1",
                "support_status": "supported",
                "risk": "unexpected",
                "evidence": [
                    {
                        "citation_key": "KeyA",
                        "source_title": "Alert Triage in Practice",
                        "evidence_quote_or_summary": "The paper studies alert triage.",
                        "supports_claim": "yes",
                    }
                ],
                "reasoning": "Direct source match.",
                "suggested_fix": "No change.",
            }
        ]
    }

    merged = merge._merge_model_citation_review([_heuristic_item()], payload)

    assert merged[0]["support_status"] == "supported"
    assert merged[0]["risk"] == "low"
    assert merged[0]["evidence_strength"] == "model_supporting_evidence"
    assert merged[0]["evidence"][0]["supports_claim"] is True
    assert merged[0]["model_reasoning"] == "Direct source match."
    assert merged[0]["suggested_fix"] == "No change."


def test_merge_model_review_normalizes_unknown_status_and_risk() -> None:
    payload = {
        "items": [
            {
                "id": "claim-1",
                "support_status": "partial",
                "risk": None,
                "evidence": [],
            }
        ]
    }

    merged = merge._merge_model_citation_review([_heuristic_item()], payload)

    assert merged[0]["support_status"] == "weakly_supported"
    assert merged[0]["risk"] == "medium"
    assert merged[0]["evidence_strength"] == "none"
