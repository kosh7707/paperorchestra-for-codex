from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.feedback import operator_feedback_attempts


def test_prepare_operator_candidate_attempt_uses_existing_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    monkeypatch.setattr(operator_feedback_attempts, "_candidate_approval_source_role", lambda imported: "qa_loop_execution")
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_ready_candidate_from_packet",
        lambda packet, current_sha, *, source_artifact_role: calls.append(("ready", packet, current_sha, source_artifact_role))
        or {"candidate_path": "candidate.tex"},
    )
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_stage_candidate_text_for_verification",
        lambda cwd, path: calls.append(("stage", cwd, path)) or "candidate text",
    )

    attempt = operator_feedback_attempts.prepare_operator_candidate_attempt(
        cwd="repo",
        provider=SimpleNamespace(),
        imported={"intent": "approve_existing_candidate"},
        packet={"packet": True},
        current_sha="sha256:paper",
        packet_prior_attempts=[],
        execution={"attempts": []},
        snapshot={"paper_text": "before"},
        attempt_index=1,
        require_compile=False,
        runtime_mode="compatibility",
        quality_mode="claim_safe",
    )

    assert attempt.candidate_result == {"candidate_path": "candidate.tex"}
    assert attempt.candidate_text == "candidate text"
    assert attempt.require_issue_progress is False
    assert calls == [("ready", {"packet": True}, "sha256:paper", "qa_loop_execution"), ("stage", "repo", "candidate.tex")]


def test_prepare_operator_candidate_attempt_preserves_generated_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    monkeypatch.setattr(
        operator_feedback_attempts,
        "_generate_operator_candidate",
        lambda cwd, provider, imported, **kwargs: calls.append(("generate", kwargs["prior_attempts"]))
        or {"candidate_path": "draft.tex", "candidate_text": "raw"},
    )
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_preserve_operator_candidate_for_attempt",
        lambda cwd, candidate_result, *, attempt_index: calls.append(("preserve", attempt_index))
        or {"candidate_path": "preserved.tex"},
    )
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_stage_candidate_text_for_verification",
        lambda cwd, path: calls.append(("stage", path)) or "preserved text",
    )

    attempt = operator_feedback_attempts.prepare_operator_candidate_attempt(
        cwd="repo",
        provider=SimpleNamespace(),
        imported={"intent": "generate_new_operator_candidate"},
        packet={},
        current_sha="sha256:paper",
        packet_prior_attempts=[{"attempt_index": 0}],
        execution={"attempts": [{"attempt_index": 1}]},
        snapshot={"paper_text": "before"},
        attempt_index=2,
        require_compile=True,
        runtime_mode="compatibility",
        quality_mode="claim_safe",
    )

    assert attempt.candidate_result == {"candidate_path": "preserved.tex"}
    assert attempt.candidate_text == "preserved text"
    assert attempt.require_issue_progress is True
    assert calls == [("generate", [{"attempt_index": 0}, {"attempt_index": 1}]), ("preserve", 2), ("stage", "preserved.tex")]


def test_prepare_operator_candidate_attempt_restores_snapshot_on_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def raise_candidate(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(operator_feedback_attempts, "_generate_operator_candidate", raise_candidate)
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_restore_session_snapshot",
        lambda cwd, snapshot: calls.append(("restore", cwd, snapshot)),
    )
    monkeypatch.setattr(
        operator_feedback_attempts,
        "_failed_operator_candidate_result",
        lambda cwd, exc: calls.append(("failed", cwd, type(exc).__name__)) or {"candidate_text": ""},
    )

    attempt = operator_feedback_attempts.prepare_operator_candidate_attempt(
        cwd="repo",
        provider=SimpleNamespace(),
        imported={"intent": "generate_new_operator_candidate"},
        packet={},
        current_sha="sha256:paper",
        packet_prior_attempts=[],
        execution={"attempts": []},
        snapshot={"paper_text": "before"},
        attempt_index=1,
        require_compile=False,
        runtime_mode="compatibility",
        quality_mode="claim_safe",
    )

    assert attempt.candidate_result == {"candidate_text": ""}
    assert attempt.candidate_text == ""
    assert attempt.require_issue_progress is True
    assert calls == [("restore", "repo", {"paper_text": "before"}), ("failed", "repo", "RuntimeError")]
