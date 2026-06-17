from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.feedback import operator_feedback_finalization


def test_finalize_operator_feedback_execution_writes_reports_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    execution = {"promotion_status": "rolled_back", "attempts": [{"attempt_index": 1}]}
    final_verification = {
        "quality_eval": {"quality": True},
        "plan": {"verdict": "human_needed"},
        "plan_path": "plan.json",
        "quality_path": "quality.json",
    }

    monkeypatch.setattr(operator_feedback_finalization, "artifact_path", lambda cwd, name: f"artifact/{name}")
    monkeypatch.setattr(operator_feedback_finalization, "load_session", lambda cwd: SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.tex")))
    monkeypatch.setattr(operator_feedback_finalization, "_file_sha256", lambda path: "sha256:after")
    monkeypatch.setattr(operator_feedback_finalization, "_operator_executor_crashed", lambda record: False)
    monkeypatch.setattr(
        operator_feedback_finalization,
        "_non_promoted_actionable_failure",
        lambda **kwargs: calls.append(("actionable", kwargs)) or {"code": "blocked"},
    )
    monkeypatch.setattr(
        operator_feedback_finalization,
        "_build_operator_incorporation_report",
        lambda **kwargs: calls.append(("incorporation_report", kwargs)) or {"report": True},
    )
    monkeypatch.setattr(operator_feedback_finalization, "write_json", lambda path, payload: calls.append(("write", path, payload)))
    monkeypatch.setattr(operator_feedback_finalization, "_verification_block", lambda payload: {"verification": True})
    monkeypatch.setattr(
        operator_feedback_finalization,
        "_operator_final_execution_update",
        lambda **kwargs: calls.append(("final_update", kwargs)) or {"verdict": "human_needed", "completed_at": "now"},
    )
    monkeypatch.setattr(operator_feedback_finalization, "_best_human_review_candidate_attempt", lambda attempts: {"attempt_index": 1})
    monkeypatch.setattr(
        operator_feedback_finalization,
        "_attach_candidate_approval_from_attempt",
        lambda execution_arg, attempt, *, execution_path: calls.append(("attach", attempt, execution_path)),
    )
    monkeypatch.setattr(
        operator_feedback_finalization,
        "append_quality_loop_history",
        lambda *args, **kwargs: calls.append(("history", args, kwargs)),
    )
    monkeypatch.setattr(operator_feedback_finalization, "_operator_history_extra", lambda execution_arg, failure: {"extra": failure})

    result = operator_feedback_finalization.finalize_operator_feedback_execution(
        cwd="repo",
        imported={"packet_sha256": "sha256:packet"},
        current_sha="sha256:before",
        execution=execution,
        final_verification=final_verification,
        final_candidate_result={"candidate_path": "candidate.tex"},
        final_incorporation=[{"id": "issue"}],
        owner_categories=["author"],
        intent="generate_new_operator_candidate",
        max_supervised_iterations=2,
    )

    assert result.execution_path == "artifact/operator_feedback.execution.json"
    assert result.execution is execution
    assert execution["completed_at"] == "now"
    assert calls[0][0] == "actionable"
    assert calls[1][0] == "incorporation_report"
    assert calls[2] == ("write", "artifact/operator_feedback.incorporation.json", {"report": True})
    assert calls[3][0] == "final_update"
    assert calls[4] == ("attach", {"attempt_index": 1}, "artifact/operator_feedback.execution.json")
    assert calls[5] == ("write", "artifact/operator_feedback.execution.json", execution)
    assert calls[6][0] == "history"
    assert calls[6][2]["verdict"] == "human_needed"


def test_finalize_operator_feedback_execution_skips_human_approval_attach_when_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    execution = {"promotion_status": "promoted", "attempts": []}
    final_verification = {
        "quality_eval": {"quality": True},
        "plan": {"verdict": "pass"},
        "plan_path": "plan.json",
        "quality_path": "quality.json",
    }

    monkeypatch.setattr(operator_feedback_finalization, "artifact_path", lambda cwd, name: f"artifact/{name}")
    monkeypatch.setattr(operator_feedback_finalization, "load_session", lambda cwd: SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.tex")))
    monkeypatch.setattr(operator_feedback_finalization, "_file_sha256", lambda path: "sha256:after")
    monkeypatch.setattr(operator_feedback_finalization, "_operator_executor_crashed", lambda record: False)
    monkeypatch.setattr(operator_feedback_finalization, "_non_promoted_actionable_failure", lambda **kwargs: None)
    monkeypatch.setattr(operator_feedback_finalization, "_build_operator_incorporation_report", lambda **kwargs: {"report": True})
    monkeypatch.setattr(operator_feedback_finalization, "write_json", lambda path, payload: calls.append(f"write:{path}"))
    monkeypatch.setattr(operator_feedback_finalization, "_verification_block", lambda payload: {"verification": True})
    monkeypatch.setattr(operator_feedback_finalization, "_operator_final_execution_update", lambda **kwargs: {"verdict": "pass", "completed_at": "now"})
    monkeypatch.setattr(operator_feedback_finalization, "_best_human_review_candidate_attempt", lambda attempts: pytest.fail("should not attach approval for promoted candidate"))
    monkeypatch.setattr(operator_feedback_finalization, "append_quality_loop_history", lambda *args, **kwargs: calls.append("history"))
    monkeypatch.setattr(operator_feedback_finalization, "_operator_history_extra", lambda execution_arg, failure: {})

    result = operator_feedback_finalization.finalize_operator_feedback_execution(
        cwd="repo",
        imported={},
        current_sha="sha256:before",
        execution=execution,
        final_verification=final_verification,
        final_candidate_result={"candidate_path": "candidate.tex"},
        final_incorporation=[],
        owner_categories=[],
        intent="approve_existing_candidate",
        max_supervised_iterations=1,
    )

    assert result.execution_path == "artifact/operator_feedback.execution.json"
    assert calls == ["write:artifact/operator_feedback.incorporation.json", "write:artifact/operator_feedback.execution.json", "history"]
