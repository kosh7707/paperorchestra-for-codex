from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_refine_current_paper_stops_when_iteration_runner_requests_stop(monkeypatch) -> None:
    from paperorchestra.engine import refine_stages
    from paperorchestra.engine.refine_iteration import RefinementIterationRun

    state = SimpleNamespace(
        artifacts=SimpleNamespace(paper_full_tex="paper.tex", latest_review_json="review.json"),
    )
    calls: list[int] = []

    monkeypatch.setattr(refine_stages, "load_session", lambda cwd: state)
    monkeypatch.setattr(refine_stages, "_planning_payloads_for_prompt", lambda cwd: ({"narrative": []}, {"claims": []}, {"placements": []}))
    monkeypatch.setattr(refine_stages, "_writer_brief_from_planning", lambda narrative, claim_map, citation_plan: {"brief": True})

    def fake_run(**kwargs: Any) -> RefinementIterationRun:
        calls.append(len(calls) + 1)
        return RefinementIterationRun(result={"iteration": len(calls), "status": "stopped"}, stop_after=True)

    monkeypatch.setattr(refine_stages, "run_refinement_iteration", fake_run)

    results = refine_stages.refine_current_paper(None, provider=object(), iterations=3)

    assert calls == [1]
    assert results == [{"iteration": 1, "status": "stopped"}]


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        artifacts=SimpleNamespace(paper_full_tex="paper.tex", latest_review_json="review.json", latest_validation_json=None),
        review_history=[],
        refinement_iteration=1,
        latest_runtime_mode="compatibility",
        notes=[],
    )


def _iteration() -> SimpleNamespace:
    return SimpleNamespace(candidate_iter=2, review_payload={"overall_score": 4.2})


def _draft(refine_iteration) -> Any:
    return refine_iteration.PreparedRefinementDraft(
        state=_state(),
        iteration=_iteration(),
        latex="accepted latex",
        worklog={"actions": []},
        lane_type="refiner",
        fallback_used=False,
        lane_notes=["note"],
        runtime_mode="compatibility",
        validation_issues=[],
        contract_regression_preservation=None,
    )


def _assessment(refine_iteration, tmp_path: Path, *, validation_payload: dict[str, Any]) -> Any:
    candidate = tmp_path / "candidate.tex"
    candidate.write_text("candidate latex", encoding="utf-8")
    return refine_iteration.RefinementCandidateAssessment(
        validation_path=tmp_path / "validation.json",
        validation_payload=validation_payload,
        candidate_tex_path=candidate,
        worklog_path=tmp_path / "worklog.json",
        latex="compile-gated latex",
        temp_state_paper="old-paper.tex",
        temp_latest_review="old-review.json",
        temp_review_history_len=3,
        previous_score=4.0,
        previous_axes={"clarity": 4.0},
        candidate_review_path="candidate-review.json",
        candidate_score=4.5,
        candidate_axes={"clarity": 4.5},
        no_op_refinement=False,
        candidate_pdf_path=tmp_path / "candidate.pdf",
        compile_error=None,
        compile_preservation=None,
        preserved_compile_error=None,
        worklog={"actions": []},
        lane_notes=["lane note"],
    )


def test_validation_failure_run_stops_and_preserves_validation_payload(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.engine import refine_iteration_outcomes as outcomes

    issue = SimpleNamespace(code="bad", to_dict=lambda: {"code": "bad"})
    state = _state()
    payload = {"issues": [{"code": "bad"}]}
    validation_path = tmp_path / "validation.json"

    monkeypatch.setattr(outcomes, "_record_validation_report", lambda cwd, **kwargs: (validation_path, payload))
    monkeypatch.setattr(outcomes, "_blocking_issues", lambda issues: list(issues))
    monkeypatch.setattr(outcomes, "_issue_messages", lambda issues: [issue.code for issue in issues])
    monkeypatch.setattr(outcomes, "save_session", lambda cwd, state: None)
    monkeypatch.setattr(outcomes, "contract_validation_failed_result", lambda **kwargs: {"kind": "validation", **kwargs})

    outcome = outcomes.record_refinement_validation_outcome(
        cwd=None,
        state=state,
        iteration=_iteration(),
        validation_issues=[issue],
        validation_name="validation.json",
        latex="bad latex",
    )

    assert outcome.validation_payload is payload
    assert outcome.failure_run is not None
    assert outcome.failure_run.stop_after is True
    assert outcome.failure_run.result["validation_payload"] is payload
    assert state.artifacts.latest_validation_json == str(validation_path)


def test_candidate_only_run_stops_and_preserves_validation_payload(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.engine import refine_iteration
    from paperorchestra.engine import refine_iteration_outcomes as outcomes

    payload = {"status": "pass"}
    state = _state()
    assessment = _assessment(refine_iteration, tmp_path, validation_payload=payload)
    recorded: dict[str, Any] = {}

    monkeypatch.setattr(outcomes, "load_session", lambda cwd: state)
    monkeypatch.setattr(outcomes, "save_session", lambda cwd, state: None)
    monkeypatch.setattr(outcomes, "_file_sha256", lambda path: "sha256:candidate")
    monkeypatch.setattr(outcomes, "apply_candidate_only_refinement_state", lambda state, **kwargs: recorded.update(kwargs))
    monkeypatch.setattr(outcomes, "candidate_only_result", lambda **kwargs: {"kind": "candidate_only", **kwargs})

    run = outcomes.candidate_only_iteration_run(
        cwd=None,
        iteration=_iteration(),
        assessment=assessment,
        contract_regression_preservation="preserved",
    )

    assert run.stop_after is True
    assert run.result["validation_payload"] is payload
    assert run.result["candidate_sha256"] == "sha256:candidate"
    assert recorded["validation_path"] == assessment.validation_path


def test_accepted_run_continues_and_preserves_validation_payload(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.engine import refine_iteration
    from paperorchestra.engine import refine_iteration_outcomes as outcomes

    payload = {"status": "pass"}
    draft = _draft(refine_iteration)
    assessment = _assessment(refine_iteration, tmp_path, validation_payload=payload)
    decision = refine_iteration.RefinementReviewDecision(
        accept=True,
        candidate_review_path="retry-review.json",
        candidate_score=4.8,
        review_retry_paths=["retry-review.json"],
        review_retry_scores=[4.8],
    )

    monkeypatch.setattr(outcomes, "artifact_path", lambda cwd, name: tmp_path / name)
    monkeypatch.setattr(outcomes, "record_accepted_refinement_lane_manifest", lambda *args, **kwargs: tmp_path / "lane.json")
    monkeypatch.setattr(outcomes, "load_session", lambda cwd: _state())
    monkeypatch.setattr(outcomes, "save_session", lambda cwd, state: None)
    monkeypatch.setattr(outcomes, "apply_accepted_refinement_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(outcomes, "accepted_refinement_result", lambda **kwargs: {"kind": "accepted", **kwargs})

    run = outcomes.accepted_iteration_run(cwd=tmp_path, draft=draft, assessment=assessment, decision=decision)

    assert run.stop_after is False
    assert run.result["validation_payload"] is payload
    assert run.result["score_after"] == 4.8
    assert (tmp_path / "paper.full.tex").read_text(encoding="utf-8") == "compile-gated latex"


def test_rejected_run_stops_and_preserves_validation_payload(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.engine import refine_iteration
    from paperorchestra.engine import refine_iteration_outcomes as outcomes

    payload = {"status": "pass"}
    draft = _draft(refine_iteration)
    assessment = _assessment(refine_iteration, tmp_path, validation_payload=payload)
    decision = refine_iteration.RefinementReviewDecision(
        accept=False,
        candidate_review_path="retry-review.json",
        candidate_score=3.8,
        review_retry_paths=["retry-review.json"],
        review_retry_scores=[3.8],
    )

    monkeypatch.setattr(outcomes, "record_rejected_refinement_lane_manifest", lambda *args, **kwargs: tmp_path / "lane.json")
    monkeypatch.setattr(outcomes, "load_session", lambda cwd: _state())
    monkeypatch.setattr(outcomes, "save_session", lambda cwd, state: None)
    monkeypatch.setattr(outcomes, "apply_rejected_refinement_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(outcomes, "rejected_refinement_result", lambda **kwargs: {"kind": "rejected", **kwargs})

    run = outcomes.rejected_iteration_run(cwd=None, draft=draft, assessment=assessment, decision=decision)

    assert run.stop_after is True
    assert run.result["validation_payload"] is payload
    assert run.result["score_after"] == 3.8
