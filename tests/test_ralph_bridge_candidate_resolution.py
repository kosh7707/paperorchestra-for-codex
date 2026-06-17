from __future__ import annotations

from pathlib import Path
from typing import Any


def _state(candidate_resolution):
    return candidate_resolution.PostActionState(
        eval_path=Path("/tmp/after-eval.json"),
        eval_payload={"tiers": {}},
        plan_path=Path("/tmp/after-plan.json"),
        plan_payload={"verdict": "continue"},
        summary={"issues": 0},
        progress={"forward_progress": True},
        verification={"quality_eval": {"path": "/tmp/after-eval.json"}},
        verdict="continue",
    )


def _request(candidate_resolution, *, outcome: str):
    return candidate_resolution.CandidateResolutionRequest(
        cwd=Path("/tmp/project"),
        paper_path=Path("/tmp/project/paper.tex"),
        original_paper="before",
        mutation_snapshot={"paper_full_tex": "paper.tex"},
        citation_review_snapshot={"path": "citation.json"},
        citation_trace_snapshot={"path": "citation.trace.json"},
        require_compile=True,
        require_live_verification=False,
        quality_mode="claim_safe",
        max_iterations=3,
        accept_mixed_provenance=True,
        before_eval={"before": True},
        before_summary={"before_issues": 2},
        actions_attempted=True,
        candidate_outcome=outcome,
        candidate_path="/tmp/project/candidate.tex",
        candidate_state={"candidate": True},
        candidate_progress={"forward_progress": True},
        auto_commit_reason="safe-progress",
        residual_citation_failures=["citation_support_missing"],
        after_codes={"citation_support_missing", "other"},
    )


def test_auto_commit_resolution_records_candidate_without_restoring(monkeypatch) -> None:
    from paperorchestra.loop_engine.ralph import bridge_candidate_resolution as resolution

    cleared: dict[str, Any] = {}
    monkeypatch.setattr(resolution, "clear_pending_manuscript_write", lambda cwd, **kwargs: cleared.update({"cwd": cwd, **kwargs}))

    result = resolution.resolve_candidate_outcome(_request(resolution, outcome="auto_commit"), _state(resolution))

    assert result.verdict == "continue"
    assert result.final_progress == {"forward_progress": True}
    assert result.execution_updates["candidate_state"] == {"candidate": True}
    assert result.execution_updates["candidate_progress"] == {"forward_progress": True}
    assert result.execution_updates["candidate_auto_commit"]["reason"] == "safe-progress"
    assert result.execution_updates["candidate_auto_commit"]["residual_citation_failures"] == ["citation_support_missing"]
    assert cleared == {
        "cwd": Path("/tmp/project"),
        "status": "resolved",
        "reason": "qa_loop_progressive_citation_candidate_committed",
    }


def test_citation_support_rejection_restores_current_and_handoff(monkeypatch) -> None:
    from paperorchestra.loop_engine.ralph import bridge_candidate_resolution as resolution

    calls: list[dict[str, Any]] = []
    restored = {
        "quality_eval_path": Path("/tmp/restored-eval.json"),
        "quality_eval": {"tiers": {"tier_1": {"status": "fail", "failing_codes": ["remaining"]}}},
        "qa_loop_plan_path": Path("/tmp/restored-plan.json"),
        "qa_loop_plan": {"verdict": "human_needed"},
        "citation_summary": {"issues": 1},
        "progress": {"forward_progress": False},
        "verification": {"quality_eval": {"path": "/tmp/restored-eval.json"}},
    }

    def fake_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, **kwargs})
        return restored

    monkeypatch.setattr(resolution, "_restore_current_after_uncommitted_candidate", fake_restore)

    result = resolution.resolve_candidate_outcome(
        _request(resolution, outcome="citation_support_rejected"),
        _state(resolution),
    )

    assert calls[0]["validation_name"] == "validation.qa-loop-step.rollback.json"
    assert result.verdict == "human_needed"
    assert result.final_eval_path == Path("/tmp/restored-eval.json")
    assert result.final_progress == {"forward_progress": False}
    assert result.execution_updates["candidate_rollback"]["reason"] == "citation_support_approval_failed"
    assert result.execution_updates["candidate_handoff"]["status"] == "human_needed_candidate_rejected_by_citation_support"
    assert result.execution_updates["candidate_state"] == {"candidate": True}
    assert result.execution_updates["restored_current_state"]["qa_loop_plan_verdict"] == "human_needed"


def test_auto_commit_gate_rejection_uses_candidate_approved_restore_name(monkeypatch) -> None:
    from paperorchestra.loop_engine.ralph import bridge_candidate_resolution as resolution

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(resolution, "_restore_current_after_uncommitted_candidate", lambda *args, **kwargs: calls.append({"args": args, **kwargs}) or None)

    result = resolution.resolve_candidate_outcome(
        _request(resolution, outcome="auto_commit_gate_rejected"),
        _state(resolution),
    )

    assert calls[0]["validation_name"] == "validation.qa-loop-step.candidate-approved-original-restored.json"
    assert result.verdict == "human_needed"
    assert result.execution_updates["candidate_rollback"]["reason"] == "citation_candidate_auto_commit_blocked"
    assert result.execution_updates["candidate_handoff"]["status"] == "human_needed_candidate_rejected_by_auto_commit_gate"
    assert result.execution_updates["candidate_progress"] == {"forward_progress": True}


def test_unsupported_candidate_outcome_fails_closed() -> None:
    import pytest

    from paperorchestra.loop_engine.ralph import bridge_candidate_resolution as resolution

    request = _request(resolution, outcome="unexpected")
    with pytest.raises(ValueError, match="Unsupported candidate outcome"):
        resolution.resolve_candidate_outcome(request, _state(resolution))
