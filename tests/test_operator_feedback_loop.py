from __future__ import annotations

from types import SimpleNamespace

from paperorchestra.feedback import operator_feedback_loop
from paperorchestra.feedback.operator_feedback_attempts import PreparedOperatorCandidateAttempt
from paperorchestra.feedback.operator_feedback_evaluation import OperatorAttemptEvaluation
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions
from paperorchestra.feedback.operator_feedback_promotion import OperatorFeedbackPromotion
from paperorchestra.feedback.operator_feedback_rollback import OperatorFeedbackRollback


def _options(**overrides) -> OperatorFeedbackOptions:
    defaults = dict(
        max_supervised_iterations=2,
        require_compile=True,
        quality_mode="claim_safe",
        max_iterations=7,
        require_live_verification=True,
        accept_mixed_provenance=True,
        runtime_mode="strict",
        citation_evidence_mode="web",
        citation_provider_name="provider",
        citation_provider_command="cmd",
    )
    defaults.update(overrides)
    return OperatorFeedbackOptions(**defaults)


def _context(*, intent: str = "generate_new_operator_candidate", execution: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        imported={"issues": []},
        packet={"packet": True},
        intent=intent,
        current_sha="sha256:paper",
        base_quality_eval={"base": True},
        packet_prior_attempts=[{"attempt_index": 0}],
        base_tier2_failures={"tier2_old"},
        base_active_failures={"active_old"},
        execution=execution or {"attempts": [], "promotion_status": "not_promoted"},
        owner_categories=["author"],
    )


def test_run_operator_feedback_attempts_promotes_first_passing_attempt(monkeypatch) -> None:
    calls = []
    context = _context()
    snapshot = {"paper_path": "paper.tex"}
    options = _options()

    monkeypatch.setattr(
        operator_feedback_loop,
        "_restore_session_snapshot",
        lambda cwd, snapshot_arg: calls.append(("restore", cwd, snapshot_arg)),
    )

    def prepare(**kwargs):
        calls.append(("prepare", kwargs["attempt_index"], kwargs["require_compile"], kwargs["runtime_mode"]))
        return PreparedOperatorCandidateAttempt(
            candidate_result={"candidate_path": "candidate.tex"},
            candidate_text="candidate text",
            require_issue_progress=True,
        )

    def evaluate(**kwargs):
        calls.append(("evaluate", kwargs["attempt_index"], kwargs["max_iterations"], kwargs["citation_provider_name"]))
        return OperatorAttemptEvaluation(
            verification={"plan": {"verdict": "attempt"}},
            incorporation=[{"issue": "done"}],
            candidate_result=kwargs["candidate_result"],
            gate_passed=True,
            gate_reasons=[],
            attempt_record={"attempt_index": kwargs["attempt_index"]},
        )

    def promote(**kwargs):
        calls.append(("promote", kwargs["attempt_index"], kwargs["candidate_result"]["candidate_path"]))
        kwargs["execution"]["promotion_status"] = "promoted"
        kwargs["attempt_record"]["promoted_canonical_verification"] = {"promoted": True}
        return OperatorFeedbackPromotion(verification={"plan": {"verdict": "pass"}})

    monkeypatch.setattr(operator_feedback_loop, "prepare_operator_candidate_attempt", prepare)
    monkeypatch.setattr(operator_feedback_loop, "evaluate_operator_candidate_attempt", evaluate)
    monkeypatch.setattr(operator_feedback_loop, "promote_operator_feedback_attempt", promote)

    result = operator_feedback_loop.run_operator_feedback_attempts(
        cwd="repo",
        provider=object(),
        context=context,
        snapshot=snapshot,
        before_text="before",
        options=options,
    )

    assert context.execution["promotion_status"] == "promoted"
    assert context.execution["attempts"] == [{"attempt_index": 1, "promoted_canonical_verification": {"promoted": True}}]
    assert result.final_incorporation == [{"issue": "done"}]
    assert result.final_candidate_result == {"candidate_path": "candidate.tex"}
    assert result.final_verification == {"plan": {"verdict": "pass"}}
    assert calls == [
        ("restore", "repo", snapshot),
        ("prepare", 1, True, "strict"),
        ("evaluate", 1, 7, "provider"),
        ("promote", 1, "candidate.tex"),
    ]


def test_run_operator_feedback_attempts_rolls_back_after_failed_attempts(monkeypatch) -> None:
    calls = []
    context = _context(execution={"attempts": [], "promotion_status": "not_promoted"})
    options = _options(max_supervised_iterations=1)

    monkeypatch.setattr(operator_feedback_loop, "_restore_session_snapshot", lambda cwd, snapshot: calls.append("restore"))
    monkeypatch.setattr(
        operator_feedback_loop,
        "prepare_operator_candidate_attempt",
        lambda **kwargs: PreparedOperatorCandidateAttempt(
            candidate_result={"candidate_path": "candidate.tex"},
            candidate_text="candidate text",
            require_issue_progress=True,
        ),
    )
    monkeypatch.setattr(
        operator_feedback_loop,
        "evaluate_operator_candidate_attempt",
        lambda **kwargs: OperatorAttemptEvaluation(
            verification={"plan": {"verdict": "attempt-fail"}},
            incorporation=[{"issue": "partial"}],
            candidate_result=kwargs["candidate_result"],
            gate_passed=False,
            gate_reasons=["failed"],
            attempt_record={"attempt_index": kwargs["attempt_index"], "gate_passed": False},
        ),
    )

    def rollback(**kwargs):
        calls.append(("rollback", kwargs["intent"], kwargs["require_compile"], kwargs["runtime_mode"]))
        kwargs["execution"]["promotion_status"] = "rolled_back"
        return OperatorFeedbackRollback(verification={"plan": {"verdict": "rolled-back"}})

    monkeypatch.setattr(operator_feedback_loop, "rollback_operator_feedback_candidate", rollback)

    result = operator_feedback_loop.run_operator_feedback_attempts(
        cwd="repo",
        provider=object(),
        context=context,
        snapshot={"paper_path": "paper.tex"},
        before_text="before",
        options=options,
    )

    assert context.execution["attempts"] == [{"attempt_index": 1, "gate_passed": False}]
    assert context.execution["promotion_status"] == "rolled_back"
    assert result.final_incorporation == [{"issue": "partial"}]
    assert result.final_verification == {"plan": {"verdict": "rolled-back"}}
    assert calls == ["restore", ("rollback", "generate_new_operator_candidate", True, "strict")]


def test_ensure_operator_feedback_final_verification_uses_no_compile_fallback(monkeypatch) -> None:
    calls = []

    def verify(cwd, *, provider, **kwargs):
        calls.append((cwd, provider, kwargs))
        return {"plan": {"verdict": "fallback"}}

    monkeypatch.setattr(operator_feedback_loop, "_verification_snapshot", verify)

    result = operator_feedback_loop.ensure_operator_feedback_final_verification(
        cwd="repo",
        provider="provider",
        execution={"promotion_status": "rolled_back"},
        final_verification=None,
        options=_options(),
    )

    assert result == {"plan": {"verdict": "fallback"}}
    assert calls[0][2]["require_compile"] is False
    assert calls[0][2]["validation_name"] == "validation.operator-feedback.no-promotion.json"
