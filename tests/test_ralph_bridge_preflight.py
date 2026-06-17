from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.loop_engine.ralph import bridge_preflight as preflight


def test_prepare_preflight_uses_plan_embedded_quality_eval_path(monkeypatch, tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    eval_path = tmp_path / "quality.json"
    before_eval = {"tiers": {"tier_1": {"failing_codes": ["missing"]}}}
    before_plan = {
        "verdict": "continue",
        "quality_eval": str(eval_path),
        "repair_actions": [
            {"code": "review_score_missing", "automation": "automatic"},
            {"code": "unsupported_future_handler", "automation": "automatic"},
        ],
    }
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(preflight, "_stage_explicit_citation_support_review", lambda cwd, path: None)
    monkeypatch.setattr(preflight, "_load_explicit_qa_loop_plan", lambda cwd, path: before_plan)
    monkeypatch.setattr(preflight, "_quality_eval_path_from_plan", lambda plan: plan["quality_eval"])
    monkeypatch.setattr(preflight, "_load_explicit_quality_eval", lambda cwd, path: (Path(path), before_eval))
    monkeypatch.setattr(preflight, "_validate_plan_quality_eval_identity", lambda plan, path: calls.append(("validate", path)))
    monkeypatch.setattr(preflight, "_citation_summary", lambda cwd: {"issue_count": 2})
    monkeypatch.setattr(preflight, "_executable_actions", lambda plan: [plan["repair_actions"][0]])
    monkeypatch.setattr(preflight, "_unsupported_executable_actions", lambda plan: [plan["repair_actions"][1]])

    result = preflight.prepare_qa_loop_preflight(
        cwd=tmp_path,
        started_at="now",
        require_live_verification=False,
        quality_mode="claim_safe",
        max_iterations=3,
        accept_mixed_provenance=False,
        quality_eval_input_path=None,
        qa_loop_plan_input_path=plan_path,
        citation_support_review_path=None,
    )

    assert result.before_eval_path == eval_path
    assert result.before_eval is before_eval
    assert result.before_plan_path == plan_path.resolve()
    assert result.before_summary == {"issue_count": 2}
    assert result.initial_verdict == "continue"
    assert result.actions == [{"code": "review_score_missing", "automation": "automatic"}]
    assert result.unsupported_actions == [{"code": "unsupported_future_handler", "automation": "automatic"}]
    assert result.execution["input_plan"] == str(plan_path.resolve())
    assert result.execution["before"]["citation_support_summary"] == {"issue_count": 2}
    assert calls == [("validate", eval_path)]


def test_prepare_preflight_rejects_plan_without_quality_eval_identity(monkeypatch, tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    monkeypatch.setattr(preflight, "_stage_explicit_citation_support_review", lambda cwd, path: None)
    monkeypatch.setattr(preflight, "_load_explicit_qa_loop_plan", lambda cwd, path: {"verdict": "continue"})
    monkeypatch.setattr(preflight, "_quality_eval_path_from_plan", lambda plan: None)

    with pytest.raises(ValueError, match="does not identify a quality-eval artifact"):
        preflight.prepare_qa_loop_preflight(
            cwd=tmp_path,
            started_at="now",
            require_live_verification=False,
            quality_mode="claim_safe",
            max_iterations=3,
            accept_mixed_provenance=False,
            quality_eval_input_path=None,
            qa_loop_plan_input_path=plan_path,
            citation_support_review_path=None,
        )
