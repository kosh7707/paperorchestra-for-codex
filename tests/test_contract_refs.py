from __future__ import annotations

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.manuscript.contract_refs import contract_context_for_text


def test_contract_context_extracts_plan_ids_and_keeps_internal_repairs_internal() -> None:
    context = contract_context_for_text("C3 needs citation support from E2 in S5, Q1, and RW2.", automation="semi_auto")

    assert context["contract_refs"] == {
        "claims": ["C3"],
        "evidence": ["E2"],
        "questions": ["Q1"],
        "sections": ["S5"],
        "visuals": [],
        "related_work": ["RW2"],
    }
    assert context["repair_class"] == "contract_internal_repair"
    assert context["plan_reapproval_required"] is False


def test_contract_context_marks_new_major_claim_as_plan_reapproval() -> None:
    context = contract_context_for_text("Add a new major claim beyond the approved plan.")

    assert context["repair_class"] == "approval_required_plan_change"
    assert context["plan_reapproval_required"] is True


def test_quality_actions_include_contract_refs_and_repair_class() -> None:
    action = _action(
        action_id="quality-eval:test",
        code="claim_strength",
        source=None,
        target="claim C7",
        automation="semi_auto",
        reason="C7 is stronger than E4 supports.",
    )

    assert action["contract_refs"]["claims"] == ["C7"]
    assert action["contract_refs"]["evidence"] == ["E4"]
    assert action["repair_class"] == "contract_internal_repair"
