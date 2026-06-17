from __future__ import annotations

from paperorchestra.feedback import operator_completion


def test_operator_executor_crashed_detects_non_none_attempt_failure() -> None:
    assert operator_completion._operator_executor_crashed({"attempts": [{"executor_failure_category": "none"}]}) is False
    assert operator_completion._operator_executor_crashed({"attempts": [{}, {"executor_failure_category": "provider_error"}]}) is True


def test_non_promoted_actionable_failure_classifies_crash_rejection_and_gate_failure() -> None:
    crash = operator_completion._non_promoted_actionable_failure(
        promoted=False,
        executor_crashed=True,
        intent="generate_new_operator_candidate",
        execution={"attempts": [{"attempt_index": 1, "executor_failure_category": "provider_error"}]},
        owner_categories=["operator", "author", "operator"],
    )
    assert crash is not None
    assert crash["reason"] == "supervised operator feedback command failed"
    assert crash["category"] == "operator_execution_error"
    assert crash["code"] == "operator_executor_crashed"
    assert crash["owner_categories"] == ["author", "operator"]
    assert crash["attempt_index"] == 1

    rejected = operator_completion._non_promoted_actionable_failure(
        promoted=False,
        executor_crashed=False,
        intent="reject_candidate_with_reason",
        execution={"attempts": []},
        owner_categories=["author"],
    )
    assert rejected is not None
    assert rejected["category"] == "operator_rejected_candidate"
    assert rejected["code"] == "operator_rejected_candidate"

    gate = operator_completion._non_promoted_actionable_failure(
        promoted=False,
        executor_crashed=False,
        intent="generate_new_operator_candidate",
        execution={"promotion_reason": "operator_candidate_failed_hard_gate", "attempts": []},
        owner_categories=["author"],
    )
    assert gate is not None
    assert gate["category"] == "operator_candidate_failed_hard_gate"
    assert gate["code"] == "operator_candidate_failed_hard_gate"

    assert operator_completion._non_promoted_actionable_failure(
        promoted=True,
        executor_crashed=True,
        intent="generate_new_operator_candidate",
        execution={"attempts": []},
        owner_categories=["author"],
    ) is None


def test_final_execution_update_and_history_extra_are_deterministic_except_timestamp() -> None:
    execution = {
        "attempts": [{"attempt_index": 1}, {"attempt_index": 2}],
        "post_promotion_qa_verdict": "pass",
    }
    update = operator_completion._operator_final_execution_update(
        execution=execution,
        promoted=False,
        executor_crashed=False,
        plan={"verdict": "pass"},
        max_supervised_iterations=3,
        after_sha="sha256:after",
        final_candidate_result={"candidate_path": "candidate.tex"},
        incorporation_path="operator_feedback.incorporation.json",
        verification_block={"quality_eval": {"path": "quality.json"}},
        actionable_failure={"code": "blocked"},
    )

    assert update["completed_at"].startswith("20")
    assert update["verdict"] == "human_needed"
    assert update["supervised_iteration_index"] == 2
    assert update["supervised_remaining"] == 1
    assert update["supervised_budget_exhausted"] is False
    assert update["manuscript_sha256_after"] == "sha256:after"
    assert update["candidate_result"] == {"candidate_path": "candidate.tex"}
    assert update["incorporation_report"] == "operator_feedback.incorporation.json"
    assert update["verification"] == {"quality_eval": {"path": "quality.json"}}
    assert update["actionable_failure"] == {"code": "blocked"}

    extra = operator_completion._operator_history_extra({**execution, **update}, {"code": "blocked"})
    assert extra == {
        "supervised_iteration_index": 2,
        "supervised_max_iterations": None,
        "supervised_remaining": 1,
        "supervised_budget_exhausted": False,
        "promotion_status": None,
        "post_promotion_qa_verdict": "pass",
        "actionable_failure": {"code": "blocked"},
    }


def test_exception_actionable_failures_keep_public_error_and_history_error_type() -> None:
    public, history = operator_completion._operator_exception_actionable_failures(
        owner_categories=["author"],
        execution={"attempts": [{"attempt_index": 3, "gate_reasons": ["blocked"]}]},
        exc=RuntimeError("boom"),
    )

    assert public["category"] == "operator_execution_error"
    assert public["code"] == "supervised_operator_feedback_command_failed"
    assert public["execution_error"] == "RuntimeError: boom"
    assert history["category"] == "operator_execution_error"
    assert history["error_type"] == "RuntimeError"
    assert "execution_error" not in history


def test_exception_history_extra_preserves_budget_math_with_minimum_attempt_index() -> None:
    extra = operator_completion._operator_exception_history_extra(
        {"supervised_max_iterations": 3, "attempts": []},
        {"code": "supervised_operator_feedback_command_failed"},
        RuntimeError("boom"),
    )
    assert extra == {
        "supervised_iteration_index": 1,
        "supervised_max_iterations": 3,
        "supervised_remaining": 2,
        "supervised_budget_exhausted": True,
        "execution_error_type": "RuntimeError",
        "promotion_status": "rolled_back",
        "actionable_failure": {"code": "supervised_operator_feedback_command_failed"},
    }


def test_exception_execution_update_carries_timestamp_and_restored_block() -> None:
    update = operator_completion._operator_exception_execution_update(
        exc=RuntimeError("boom"),
        restored_block={"error": "rollback failed"},
        actionable_failure={"code": "supervised_operator_feedback_command_failed"},
    )

    assert update["completed_at"].startswith("20")
    assert update["verdict"] == "execution_error"
    assert update["promotion_status"] == "rolled_back"
    assert update["post_promotion_qa_verdict"] is None
    assert update["error"] == "boom"
    assert update["candidate_rollback"] == {"reason": "exception", "restored_verification": {"error": "rollback failed"}}
    assert update["verification"] == {"restored_after_exception": {"error": "rollback failed"}}
    assert update["actionable_failure"] == {"code": "supervised_operator_feedback_command_failed"}
