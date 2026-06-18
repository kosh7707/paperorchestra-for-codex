from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import operator_issue_contract as issues


def _packet() -> dict[str, str]:
    return {"packet_sha256": "p" * 64}


def _issue(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_artifact_role": "quality_eval",
        "source_item_key": "tier2:unsupported_claim",
        "target_section": "Results",
        "severity": "high",
        "rationale": "Experiment result lacks support.",
        "suggested_action": "Add benchmark evidence.",
        "authority_class": "evidence",
    }
    base["id"] = issues.derive_operator_issue_id(
        _packet()["packet_sha256"],
        source_artifact_role=str(base["source_artifact_role"]),
        source_item_key=str(base["source_item_key"]),
        target_section=str(base["target_section"]),
        rationale=str(base["rationale"]),
        suggested_action=str(base["suggested_action"]),
    )
    base.update(overrides)
    return base


def test_derive_operator_issue_id_normalizes_whitespace_case_in_text_fields() -> None:
    first = issues.derive_operator_issue_id(
        "p" * 64,
        source_artifact_role="quality_eval",
        source_item_key="issue-1",
        target_section="Results",
        rationale=" Missing   Evidence ",
        suggested_action=" Add   Citation ",
    )
    second = issues.derive_operator_issue_id(
        "p" * 64,
        source_artifact_role="quality_eval",
        source_item_key="issue-1",
        target_section="Results",
        rationale="missing evidence",
        suggested_action="add citation",
    )

    assert first == second
    assert first.startswith("opfb-")


def test_validate_operator_issue_normalizes_source_provenance_and_owner() -> None:
    normalized = issues._validate_operator_issue(_issue(), _packet())

    assert normalized["source"] == issues.OPERATOR_SOURCE
    assert normalized["not_independent_human_review"] is True
    assert normalized["owner_category"] == "experiment"


def test_validate_operator_issue_rejects_stale_id_or_invalid_owner() -> None:
    with pytest.raises(ContractError, match="id is not derivable"):
        issues._validate_operator_issue(_issue(id="opfb-stale"), _packet())

    with pytest.raises(ContractError, match="invalid owner_category"):
        issues._validate_operator_issue(_issue(owner_category="nonsense"), _packet())

    with pytest.raises(ContractError, match="source must be codex_operator"):
        issues._validate_operator_issue(_issue(source="independent_human_review"), _packet())

    with pytest.raises(ContractError, match="must not claim independent human review"):
        issues._validate_operator_issue(_issue(not_independent_human_review=False), _packet())


def test_action_for_issue_preserves_operator_provenance() -> None:
    normalized = issues._validate_operator_issue(_issue(), _packet())
    action = issues._action_for_issue(normalized)

    assert action == {
        "action_id": f"operator-feedback:{normalized['id']}",
        "code": "operator_feedback_issue",
        "automation": "semi_auto",
        "source_issue_id": normalized["id"],
        "target_section": "Results",
        "authority_class": "evidence",
        "owner_category": "experiment",
        "reason": "Experiment result lacks support.",
        "suggested_action": "Add benchmark evidence.",
        "source": issues.OPERATOR_SOURCE,
        "not_independent_human_review": True,
    }


def test_normalize_operator_intent_requires_single_valid_intent_or_matching_primary() -> None:
    assert issues._normalize_operator_intent({"intent": "generate_new_operator_candidate"}) == "generate_new_operator_candidate"
    assert (
        issues._normalize_operator_intent({"issues": [{"action_kind": "approve_existing_candidate"}]})
        == "approve_existing_candidate"
    )
    assert (
        issues._normalize_operator_intent({"actions": [{"action_kind": "reject_candidate_with_reason"}]})
        == "reject_candidate_with_reason"
    )
    assert issues._normalize_operator_intent(
        {
            "intents": ["reject_candidate_with_reason", "reject_candidate_with_reason"],
            "primary_intent": "reject_candidate_with_reason",
        }
    ) == "reject_candidate_with_reason"

    with pytest.raises(ContractError, match="unsupported operator feedback intent"):
        issues._normalize_operator_intent({"intent": "invent_new_policy"})
    with pytest.raises(ContractError, match="exactly one"):
        issues._normalize_operator_intent({"intents": ["approve_existing_candidate", "generate_new_operator_candidate"]})
    with pytest.raises(ContractError, match="primary_intent must be included"):
        issues._normalize_operator_intent(
            {"intents": ["approve_existing_candidate"], "primary_intent": "reject_candidate_with_reason"}
        )
