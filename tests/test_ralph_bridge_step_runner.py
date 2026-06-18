from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.ralph import bridge


class DummyProvider:
    pass


def _preflight() -> SimpleNamespace:
    return SimpleNamespace(
        before_eval_path="before-eval.json",
        before_eval={"before": True},
        before_plan_path="before-plan.json",
        before_summary={"citations": 1},
        initial_verdict="continue",
        execution={"actions_attempted": [], "actions_skipped": []},
        actions=[{"code": "repair"}],
        unsupported_actions=[{"code": "unsupported"}],
    )


def test_run_qa_loop_step_preserves_success_flow_and_patch_surface(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    preflight = _preflight()
    rollback = SimpleNamespace(paper_path=tmp_path / "paper.tex", original_paper="original")
    post_action = SimpleNamespace(progress={"improved": True})
    resolved = SimpleNamespace(
        verdict="continue",
        execution_updates={"resolved": True},
        final_eval={"after": True},
        final_eval_path="after-eval.json",
        final_plan_path="after-plan.json",
        final_summary={"citations": 2},
        final_progress={"delta": 1},
        final_verification={"ok": True},
    )

    monkeypatch.setattr(bridge, "recover_pending_manuscript_write", lambda cwd: calls.append("recover"))
    monkeypatch.setattr(bridge, "utc_now_iso", lambda: "now")
    monkeypatch.setattr(bridge, "prepare_qa_loop_preflight", lambda **kwargs: calls.append("preflight") or preflight)
    monkeypatch.setattr(bridge, "record_unsupported_actions", lambda execution, actions: calls.append("unsupported"))
    monkeypatch.setattr(bridge, "capture_qa_loop_rollback_context", lambda cwd: calls.append("rollback") or rollback)
    monkeypatch.setattr(bridge, "get_citation_support_provider", lambda *args, **kwargs: calls.append("citation-provider") or "citation-provider")

    def dispatch(actions, execution, context):
        calls.append(f"dispatch:{context.citation_provider}:{context.paper_path.name}")
        execution["actions_attempted"].append({"code": "repair"})
        return SimpleNamespace(citation_candidate_applied=False, citation_candidate_path=None)

    monkeypatch.setattr(bridge, "dispatch_qa_loop_actions", dispatch)
    monkeypatch.setattr(bridge, "verify_after_qa_loop_actions", lambda **kwargs: calls.append("verify") or post_action)
    monkeypatch.setattr(bridge, "resolve_post_dispatch_candidate", lambda **kwargs: calls.append("resolve") or resolved)
    monkeypatch.setattr(bridge, "should_override_no_progress", lambda **kwargs: False)

    def finish(**kwargs):
        calls.append(f"finish:{kwargs['verdict']}")
        return bridge.StepResult(path=Path("execution.json"), payload=kwargs["execution"], exit_code=0)

    monkeypatch.setattr(bridge, "finish_successful_step", finish)

    result = bridge.run_qa_loop_step(tmp_path, DummyProvider())

    assert calls == [
        "recover",
        "preflight",
        "unsupported",
        "rollback",
        "citation-provider",
        "dispatch:citation-provider:paper.tex",
        "verify",
        "resolve",
        "finish:continue",
    ]
    assert result.payload["resolved"] is True


def test_run_qa_loop_step_restores_candidate_on_post_action_error(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    preflight = _preflight()
    rollback = SimpleNamespace(paper_path=tmp_path / "paper.tex", original_paper="original")

    monkeypatch.setattr(bridge, "recover_pending_manuscript_write", lambda cwd: None)
    monkeypatch.setattr(bridge, "utc_now_iso", lambda: "now")
    monkeypatch.setattr(bridge, "prepare_qa_loop_preflight", lambda **kwargs: preflight)
    monkeypatch.setattr(bridge, "record_unsupported_actions", lambda execution, actions: None)
    monkeypatch.setattr(bridge, "capture_qa_loop_rollback_context", lambda cwd: rollback)
    monkeypatch.setattr(bridge, "get_citation_support_provider", lambda *args, **kwargs: "citation-provider")
    monkeypatch.setattr(
        bridge,
        "dispatch_qa_loop_actions",
        lambda *args, **kwargs: SimpleNamespace(citation_candidate_applied=True, citation_candidate_path="candidate.tex"),
    )
    monkeypatch.setattr(
        bridge,
        "verify_after_qa_loop_actions",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("post action failed")),
    )
    monkeypatch.setattr(
        bridge,
        "restore_candidate_after_exception",
        lambda **kwargs: calls.append(f"restore:{kwargs['citation_candidate_applied']}"),
    )

    def finish_error(**kwargs):
        calls.append(f"finish-error:{kwargs['error']}")
        return bridge.StepResult(path=Path("execution.json"), payload=kwargs["execution"], exit_code=2)

    monkeypatch.setattr(bridge, "finish_execution_error", finish_error)

    result = bridge.run_qa_loop_step(tmp_path, DummyProvider())

    assert calls == ["restore:True", "finish-error:post action failed"]
    assert result.exit_code == 2
