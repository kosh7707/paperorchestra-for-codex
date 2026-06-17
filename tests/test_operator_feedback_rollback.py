from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.feedback import operator_feedback_rollback


def test_rollback_operator_feedback_candidate_restores_snapshot_and_records_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    rollback_verification = {"quality_eval": {"q": True}, "plan": {"verdict": "human_needed"}}

    monkeypatch.setattr(operator_feedback_rollback, "_restore_session_snapshot", lambda cwd, snapshot: calls.append(("restore", cwd, snapshot)))
    monkeypatch.setattr(
        operator_feedback_rollback,
        "_verification_snapshot",
        lambda *args, **kwargs: calls.append(("verify", kwargs["validation_name"], kwargs["require_compile"])) or rollback_verification,
    )
    monkeypatch.setattr(operator_feedback_rollback, "_verification_block", lambda payload: {"restored": True})

    execution = {"attempts": []}
    result = operator_feedback_rollback.rollback_operator_feedback_candidate(
        cwd="repo",
        provider=SimpleNamespace(),
        snapshot={"paper_text": "before"},
        execution=execution,
        intent="reject_candidate_with_reason",
        require_compile=True,
        quality_mode="claim_safe",
        max_iterations=3,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.verification is rollback_verification
    assert execution["promotion_status"] == "rolled_back"
    assert execution["promotion_reason"] == "operator_rejected_candidate"
    assert execution["candidate_rollback"] == {
        "reason": "operator_rejected_candidate",
        "restored_verification": {"restored": True},
    }
    assert calls == [("restore", "repo", {"paper_text": "before"}), ("verify", "validation.operator-feedback.rollback.json", True)]


def test_rollback_operator_feedback_candidate_records_failed_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operator_feedback_rollback, "_restore_session_snapshot", lambda cwd, snapshot: None)
    monkeypatch.setattr(operator_feedback_rollback, "_verification_snapshot", lambda *args, **kwargs: {"quality_eval": {}})
    monkeypatch.setattr(operator_feedback_rollback, "_verification_block", lambda payload: {"restored": True})

    execution = {"attempts": [{"attempt_index": 1}]}
    result = operator_feedback_rollback.rollback_operator_feedback_candidate(
        cwd="repo",
        provider=SimpleNamespace(),
        snapshot={},
        execution=execution,
        intent="generate_new_operator_candidate",
        require_compile=False,
        quality_mode="claim_safe",
        max_iterations=3,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.verification == {"quality_eval": {}}
    assert execution["promotion_status"] == "rolled_back"
    assert execution["promotion_reason"] == "operator_candidate_failed_hard_gate"
    assert execution["candidate_rollback"] == {
        "reason": "supervised_candidate_failed_hard_gate",
        "restored_verification": {"restored": True},
    }
