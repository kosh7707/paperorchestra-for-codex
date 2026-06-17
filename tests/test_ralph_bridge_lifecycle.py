from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.ralph import bridge_lifecycle as lifecycle


def test_record_unsupported_actions_marks_skipped_handlers() -> None:
    execution = {"actions_skipped": []}

    lifecycle.record_unsupported_actions(execution, [{"code": "future"}, {"code": "manual"}])

    assert execution["actions_skipped"] == [
        {"code": "future", "reason": "unsupported_handler"},
        {"code": "manual", "reason": "unsupported_handler"},
    ]


def test_finish_execution_error_records_budget_consuming_attempt(monkeypatch, tmp_path: Path) -> None:
    written: list[dict] = []
    history: list[dict] = []
    artifact_path = tmp_path / "execution.json"

    monkeypatch.setattr(lifecycle, "_write_execution_artifact", lambda cwd, payload: written.append(dict(payload)) or artifact_path)
    monkeypatch.setattr(lifecycle, "append_quality_loop_history", lambda *args, **kwargs: history.append({"args": args, "kwargs": kwargs}))

    execution = {"actions_attempted": [{"code": "x"}], "actions_skipped": []}
    result = lifecycle.finish_execution_error(
        cwd=tmp_path,
        execution=execution,
        before_eval={"eval": True},
        before_plan_path=Path("plan.json"),
        before_eval_path=Path("eval.json"),
        error=RuntimeError("boom"),
        citation_candidate_applied=True,
    )

    assert result.path == artifact_path
    assert result.exit_code == 40
    assert written[0]["verdict"] == "execution_error"
    assert written[0]["candidate_rollback"] == {"reason": "exception"}
    assert history[0]["kwargs"]["event_type"] == "qa_loop_step"
    assert history[0]["kwargs"]["consumes_budget"] is True
