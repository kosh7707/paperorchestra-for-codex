from __future__ import annotations

from paperorchestra.feedback import operator_feedback_promotion
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions


def test_promote_operator_feedback_attempt_records_side_effects(monkeypatch) -> None:
    calls = []
    execution = {}
    attempt_record = {}
    candidate_result = {"candidate_path": "candidate.tex"}
    options = OperatorFeedbackOptions(require_compile=True, runtime_mode="strict")
    verification = {"plan": {"verdict": "pass"}}

    monkeypatch.setattr(
        operator_feedback_promotion,
        "_promote_candidate_text",
        lambda cwd, candidate_path, paper_path: calls.append(("promote_text", cwd, candidate_path, paper_path)),
    )

    def verify(cwd, *, provider, **kwargs):
        calls.append(("verify", cwd, provider, kwargs))
        return verification

    monkeypatch.setattr(operator_feedback_promotion, "_verification_snapshot", verify)
    monkeypatch.setattr(operator_feedback_promotion, "_verification_block", lambda payload: {"block": payload["plan"]})

    result = operator_feedback_promotion.promote_operator_feedback_attempt(
        cwd="repo",
        provider="provider",
        snapshot={"paper_path": "paper.tex"},
        execution=execution,
        candidate_result=candidate_result,
        attempt_record=attempt_record,
        attempt_index=3,
        options=options,
    )

    assert result.verification is verification
    assert execution == {
        "promotion_status": "promoted",
        "promotion_reason": "operator_candidate_passed_hard_gate",
        "post_promotion_qa_verdict": "pass",
    }
    assert attempt_record == {"promoted_canonical_verification": {"block": {"verdict": "pass"}}}
    assert calls[0] == ("promote_text", "repo", "candidate.tex", "paper.tex")
    assert calls[1][0:3] == ("verify", "repo", "provider")
    assert calls[1][3]["validation_name"] == "validation.operator-feedback.promoted-03.json"
    assert calls[1][3]["require_compile"] is True
    assert calls[1][3]["runtime_mode"] == "strict"
