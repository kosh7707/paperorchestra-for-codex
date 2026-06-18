from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import human_needed_decision as decision


def test_resolve_decision_kind_requires_candidate_role_for_approval() -> None:
    assert (
        decision._resolve_decision_kind("reject this candidate", None, candidate_role="qa_loop_execution")
        == "reject_candidate_with_reason"
    )
    assert (
        decision._resolve_decision_kind("approve the ready candidate", None, candidate_role="qa_loop_execution")
        == "approve_existing_candidate"
    )
    assert (
        decision._resolve_decision_kind("좋아 계속 진행", None, candidate_role="qa_loop_execution")
        == "generate_new_operator_candidate"
    )

    with pytest.raises(ContractError, match="requires an actionable candidate approval artifact"):
        decision._resolve_decision_kind("approve the ready candidate", "approve_existing_candidate", candidate_role=None)


def test_select_action_requires_action_id_for_multiple_non_candidate_actions() -> None:
    actions = [
        {"id": "citation", "automation": "human_needed"},
        {"action_id": "figure", "automation": "human_needed"},
    ]

    with pytest.raises(ContractError, match="multiple human_needed actions"):
        decision._select_action(actions, None, candidate_role=None)

    assert decision._select_action(actions, "figure", candidate_role=None) == actions[1]
    assert decision._select_action(actions, None, candidate_role="qa_loop_execution") is None


def test_classify_action_prefers_candidate_role_and_keyword_categories() -> None:
    assert decision._classify_action({"code": "citation_missing"}, candidate_role="qa_loop_execution") == "candidate_approval"
    assert decision._classify_action({"reason": "Figure caption needs judgment"}) == "figure_grounding_decision"
    assert decision._classify_action({"reason": "Compile dependency missing"}) == "environment_dependency"
    assert decision._classify_action({"reason": "Reviewer independence required"}) == "reviewer_independence"
    assert decision._classify_action({"code": "custom_handler"}) == "general_operator_feedback"
    assert decision._classify_action(None) == "unsupported_handler"


def test_human_needed_actions_reads_only_human_needed_plan_actions(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "repair_actions": [
                    {"id": "human", "automation": "human_needed"},
                    {"id": "auto", "automation": "auto"},
                ]
            }
        ),
        encoding="utf-8",
    )
    packet = {"artifacts": [{"role": "qa_loop_plan", "path": str(plan_path)}]}

    assert decision._human_needed_actions(packet) == [{"id": "human", "automation": "human_needed"}]

    plan_path.write_text("{not-json", encoding="utf-8")
    assert decision._human_needed_actions(packet) == []
