from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.feedback import operator_feedback_evaluation


def _patch_common(monkeypatch: pytest.MonkeyPatch, *, gate_passed: bool = True, repeats: bool = False) -> list[tuple]:
    calls: list[tuple] = []
    verification = {
        "quality_eval": {"quality": True},
        "validation_payload": {"valid": True},
        "compile_payload": {"compiled": True},
    }
    monkeypatch.setattr(operator_feedback_evaluation, "_verification_snapshot", lambda *args, **kwargs: calls.append(("verify", kwargs["validation_name"])) or verification)
    monkeypatch.setattr(operator_feedback_evaluation, "_quality_failing_codes", lambda payload: ["new_active"])
    monkeypatch.setattr(operator_feedback_evaluation, "_tier_failing_codes", lambda payload, tier: ["tier2_new"])
    monkeypatch.setattr(
        operator_feedback_evaluation,
        "_issue_incorporation_detailed",
        lambda issues, before, candidate, *, blocking_codes: calls.append(("incorporation", issues, before, candidate, blocking_codes)) or [{"id": "inc"}],
    )
    monkeypatch.setattr(operator_feedback_evaluation, "load_session", lambda cwd: SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.tex")))
    monkeypatch.setattr(operator_feedback_evaluation, "_file_sha256", lambda path: "changed" if path == "paper.tex" else "file")
    monkeypatch.setattr(operator_feedback_evaluation, "_protected_supported_citation_regressions", lambda imported, text: [{"code": "protected"}])
    monkeypatch.setattr(operator_feedback_evaluation, "_candidate_hard_gate", lambda **kwargs: calls.append(("gate", kwargs)) or (gate_passed, ["base_reason"]))
    monkeypatch.setattr(operator_feedback_evaluation, "_sha256_digest", lambda value: "digest" if value else "")
    monkeypatch.setattr(operator_feedback_evaluation, "_sha256_prefixed", lambda value: f"sha256:{value}" if value else "")
    monkeypatch.setattr(operator_feedback_evaluation, "_repeats_non_promotable_candidate", lambda attempts, sha: calls.append(("repeat", attempts, sha)) or repeats)
    monkeypatch.setattr(operator_feedback_evaluation, "_active_tier2_metric_delta", lambda *args, **kwargs: {"delta": True})
    monkeypatch.setattr(operator_feedback_evaluation, "_verification_block", lambda payload: {"verification": True})

    def build_attempt(**kwargs):
        calls.append(("attempt_record", kwargs))
        return {"record": True, "gate_passed": kwargs["gate_passed"], "gate_reasons": kwargs["gate_reasons"]}

    monkeypatch.setattr(operator_feedback_evaluation, "_build_operator_attempt_record", build_attempt)
    return calls


def test_evaluate_operator_candidate_attempt_builds_gate_and_attempt_record(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_common(monkeypatch, gate_passed=True)

    result = operator_feedback_evaluation.evaluate_operator_candidate_attempt(
        cwd="repo",
        provider=SimpleNamespace(),
        imported={"issues": [{"id": "issue"}]},
        before_text="before",
        current_sha="sha256:before",
        base_quality_eval={"base": True},
        base_tier2_failures={"tier2_old"},
        base_active_failures={"old_active"},
        packet_prior_attempts=[{"attempt_index": 0}],
        execution={"attempts": []},
        intent="generate_new_operator_candidate",
        attempt_index=2,
        candidate_result={"candidate_path": "candidate.tex", "candidate_sha256": "candidate"},
        candidate_text="candidate text",
        require_issue_progress=True,
        require_compile=False,
        quality_mode="claim_safe",
        max_iterations=10,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.gate_passed is True
    assert result.gate_reasons == ["base_reason"]
    assert result.incorporation == [{"id": "inc"}]
    assert result.verification["quality_eval"] == {"quality": True}
    assert result.attempt_record == {"record": True, "gate_passed": True, "gate_reasons": ["base_reason"]}
    assert ("verify", "validation.operator-feedback.attempt-02.json") in calls
    assert calls[1] == ("incorporation", [{"id": "issue"}], "before", "candidate text", ["new_active"])
    gate_call = next(call for call in calls if call[0] == "gate")[1]
    assert gate_call["manuscript_changed"] is True
    assert gate_call["new_tier2_failures"] == ["tier2_new"]
    assert gate_call["resolved_active_failures"] == ["old_active"]
    attempt_call = next(call for call in calls if call[0] == "attempt_record")[1]
    assert attempt_call["candidate_sha_for_attempt"] == "sha256:digest"
    assert attempt_call["active_tier2_metric_delta"] == {"delta": True}
    assert attempt_call["protected_regressions"] == [{"code": "protected"}]


def test_evaluate_operator_candidate_attempt_marks_preserved_and_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_common(monkeypatch, gate_passed=True, repeats=True)

    result = operator_feedback_evaluation.evaluate_operator_candidate_attempt(
        cwd="repo",
        provider=SimpleNamespace(),
        imported={"issues": []},
        before_text="before",
        current_sha="sha256:before",
        base_quality_eval={"base": True},
        base_tier2_failures=set(),
        base_active_failures=set(),
        packet_prior_attempts=[{"attempt_index": 0}],
        execution={"attempts": [{"attempt_index": 1}]},
        intent="generate_new_operator_candidate",
        attempt_index=2,
        candidate_result={"candidate_path": "candidate.tex", "preserved_prior_after_contract_regression": True},
        candidate_text="candidate text",
        require_issue_progress=True,
        require_compile=False,
        quality_mode="claim_safe",
        max_iterations=10,
        require_live_verification=False,
        accept_mixed_provenance=False,
        runtime_mode="compatibility",
        citation_evidence_mode="web",
        citation_provider_name=None,
        citation_provider_command=None,
    )

    assert result.gate_passed is False
    assert result.gate_reasons == ["base_reason", "contract_regression_preserved_prior", "repeated_non_promotable_candidate"]
    assert result.attempt_record["gate_passed"] is False
    repeat_call = next(call for call in calls if call[0] == "repeat")
    assert repeat_call[1] == [{"attempt_index": 0}, {"attempt_index": 1}]
    assert repeat_call[2] == "sha256:file"
