from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.feedback import operator_feedback_exception


def test_handle_operator_feedback_exception_restores_and_records_history(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    execution = {"supervised_max_iterations": 2, "attempts": []}
    verification = {
        "quality_eval": {"quality": True},
        "plan_path": "plan.json",
        "quality_path": "quality.json",
        "validation_path": "validation.json",
    }

    monkeypatch.setattr(operator_feedback_exception, "_restore_session_snapshot", lambda cwd, snapshot: calls.append(("restore", cwd, snapshot)))
    monkeypatch.setattr(
        operator_feedback_exception,
        "_verification_snapshot",
        lambda *args, **kwargs: calls.append(("verify", kwargs["validation_name"], kwargs["require_compile"])) or verification,
    )
    monkeypatch.setattr(operator_feedback_exception, "_verification_block", lambda payload: {"restored": True})
    monkeypatch.setattr(
        operator_feedback_exception,
        "_operator_exception_actionable_failures",
        lambda **kwargs: calls.append(("failures", kwargs["owner_categories"], type(kwargs["exc"]).__name__))
        or ({"public": True}, {"history": True}),
    )
    monkeypatch.setattr(
        operator_feedback_exception,
        "_operator_exception_execution_update",
        lambda **kwargs: calls.append(("update", kwargs["restored_block"], kwargs["actionable_failure"])) or {"verdict": "execution_error"},
    )
    monkeypatch.setattr(operator_feedback_exception, "artifact_path", lambda cwd, name: f"artifact/{name}")
    monkeypatch.setattr(operator_feedback_exception, "write_json", lambda path, payload: calls.append(("write", path, payload)))
    monkeypatch.setattr(
        operator_feedback_exception,
        "append_quality_loop_history",
        lambda *args, **kwargs: calls.append(("history", args, kwargs)),
    )
    monkeypatch.setattr(operator_feedback_exception, "_operator_exception_history_extra", lambda execution_arg, failure, exc: {"extra": True})

    result = operator_feedback_exception.handle_operator_feedback_exception(
        cwd="repo",
        provider=SimpleNamespace(),
        snapshot={"paper_text": "before"},
        execution=execution,
        owner_categories=["author"],
        exc=RuntimeError("boom"),
        quality_mode="claim_safe",
        max_iterations=3,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.execution_path == "artifact/operator_feedback.execution.json"
    assert result.execution is execution
    assert execution["verdict"] == "execution_error"
    assert calls[0] == ("restore", "repo", {"paper_text": "before"})
    assert calls[1] == ("verify", "validation.operator-feedback.exception-rollback.json", False)
    assert calls[2] == ("failures", ["author"], "RuntimeError")
    assert calls[3] == ("update", {"restored": True}, {"public": True})
    assert calls[4] == ("write", "artifact/operator_feedback.execution.json", execution)
    assert calls[5][0] == "history"
    assert calls[5][2]["verdict"] == "execution_error"


def test_handle_operator_feedback_exception_records_verification_error_without_history(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    execution = {"supervised_max_iterations": 1, "attempts": []}

    def raise_verification(*args, **kwargs):
        raise ValueError("verification failed")

    monkeypatch.setattr(operator_feedback_exception, "_restore_session_snapshot", lambda cwd, snapshot: calls.append(("restore", cwd, snapshot)))
    monkeypatch.setattr(operator_feedback_exception, "_verification_snapshot", raise_verification)
    monkeypatch.setattr(
        operator_feedback_exception,
        "_operator_exception_actionable_failures",
        lambda **kwargs: ({"public": True}, {"history": True}),
    )
    monkeypatch.setattr(
        operator_feedback_exception,
        "_operator_exception_execution_update",
        lambda **kwargs: calls.append(("update", kwargs["restored_block"])) or {"verdict": "execution_error"},
    )
    monkeypatch.setattr(operator_feedback_exception, "artifact_path", lambda cwd, name: f"artifact/{name}")
    monkeypatch.setattr(operator_feedback_exception, "write_json", lambda path, payload: calls.append(("write", path, payload)))
    monkeypatch.setattr(operator_feedback_exception, "append_quality_loop_history", lambda *args, **kwargs: pytest.fail("no quality_eval means no history append"))

    result = operator_feedback_exception.handle_operator_feedback_exception(
        cwd="repo",
        provider=SimpleNamespace(),
        snapshot={},
        execution=execution,
        owner_categories=[],
        exc=RuntimeError("boom"),
        quality_mode="claim_safe",
        max_iterations=3,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.execution_path == "artifact/operator_feedback.execution.json"
    assert calls[1] == ("update", {"error": "ValueError: verification failed"})
    assert calls[2][0] == "write"
