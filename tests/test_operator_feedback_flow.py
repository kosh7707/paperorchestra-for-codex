from __future__ import annotations

from types import SimpleNamespace

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import operator_feedback_flow
from paperorchestra.feedback.operator_feedback_loop import OperatorFeedbackLoopResult
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions


def _context(execution: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        imported={"intent": "generate_new_operator_candidate"},
        current_sha="sha256:paper",
        execution=execution or {"attempts": [], "promotion_status": "not_promoted"},
        owner_categories=["author"],
        intent="generate_new_operator_candidate",
    )


def test_apply_operator_feedback_rejects_invalid_iteration_count_before_context_load(monkeypatch) -> None:
    monkeypatch.setattr(
        operator_feedback_flow,
        "load_operator_feedback_context",
        lambda **kwargs: pytest.fail("context must not load after invalid max_supervised_iterations"),
    )

    with pytest.raises(ContractError, match="max_supervised_iterations must be >= 1"):
        operator_feedback_flow.apply_operator_feedback(
            cwd="repo",
            provider=object(),
            imported_feedback_path="imported.json",
            max_supervised_iterations=0,
        )


def test_apply_operator_feedback_runs_loop_fallback_and_finalization(monkeypatch) -> None:
    calls = []
    context = _context()
    final_verification = {"plan": {"verdict": "pass"}}

    monkeypatch.setattr(
        operator_feedback_flow,
        "load_operator_feedback_context",
        lambda **kwargs: calls.append(("context", kwargs["max_supervised_iterations"])) or context,
    )
    monkeypatch.setattr(
        operator_feedback_flow,
        "_session_snapshot",
        lambda cwd: calls.append(("snapshot", cwd)) or {"paper_text": "before"},
    )

    def run_loop(**kwargs):
        options = kwargs["options"]
        calls.append(
            (
                "loop",
                kwargs["cwd"],
                kwargs["before_text"],
                isinstance(options, OperatorFeedbackOptions),
                options.require_compile,
                options.runtime_mode,
            )
        )
        return OperatorFeedbackLoopResult(
            final_incorporation=[{"issue": "done"}],
            final_verification=None,
            final_candidate_result={"candidate_path": "candidate.tex"},
        )

    def ensure(**kwargs):
        calls.append(("ensure", kwargs["execution"], kwargs["final_verification"]))
        return final_verification

    def finalize(**kwargs):
        calls.append(
            (
                "finalize",
                kwargs["imported"],
                kwargs["current_sha"],
                kwargs["final_verification"],
                kwargs["final_candidate_result"],
                kwargs["final_incorporation"],
                kwargs["max_supervised_iterations"],
            )
        )
        return SimpleNamespace(execution_path="artifact/operator_feedback.execution.json", execution={"verdict": "pass"})

    monkeypatch.setattr(operator_feedback_flow, "run_operator_feedback_attempts", run_loop)
    monkeypatch.setattr(operator_feedback_flow, "ensure_operator_feedback_final_verification", ensure)
    monkeypatch.setattr(operator_feedback_flow, "finalize_operator_feedback_execution", finalize)

    path, execution = operator_feedback_flow.apply_operator_feedback(
        cwd="repo",
        provider="provider",
        imported_feedback_path="imported.json",
        max_supervised_iterations=3,
        require_compile=True,
        runtime_mode="strict",
    )

    assert path == "artifact/operator_feedback.execution.json"
    assert execution == {"verdict": "pass"}
    assert calls == [
        ("context", 3),
        ("snapshot", "repo"),
        ("loop", "repo", "before", True, True, "strict"),
        ("ensure", context.execution, None),
        (
            "finalize",
            context.imported,
            "sha256:paper",
            final_verification,
            {"candidate_path": "candidate.tex"},
            [{"issue": "done"}],
            3,
        ),
    ]


def test_apply_operator_feedback_routes_loop_exception_to_exception_handler(monkeypatch) -> None:
    calls = []
    context = _context(execution={"attempts": [], "promotion_status": "not_promoted"})
    snapshot = {"paper_text": "before", "paper_path": "paper.tex"}

    monkeypatch.setattr(operator_feedback_flow, "load_operator_feedback_context", lambda **kwargs: context)
    monkeypatch.setattr(operator_feedback_flow, "_session_snapshot", lambda cwd: snapshot)

    def raise_loop(**kwargs):
        raise RuntimeError("boom")

    def handle(**kwargs):
        calls.append(
            (
                kwargs["snapshot"],
                kwargs["execution"],
                kwargs["owner_categories"],
                type(kwargs["exc"]).__name__,
                kwargs["quality_mode"],
                kwargs["runtime_mode"],
                kwargs["citation_provider_command"],
            )
        )
        return SimpleNamespace(execution_path="artifact/operator_feedback.execution.json", execution={"verdict": "error"})

    monkeypatch.setattr(operator_feedback_flow, "run_operator_feedback_attempts", raise_loop)
    monkeypatch.setattr(operator_feedback_flow, "handle_operator_feedback_exception", handle)

    path, execution = operator_feedback_flow.apply_operator_feedback(
        cwd="repo",
        provider="provider",
        imported_feedback_path="imported.json",
        quality_mode="claim_safe",
        runtime_mode="strict",
        citation_provider_command="cmd",
    )

    assert path == "artifact/operator_feedback.execution.json"
    assert execution == {"verdict": "error"}
    assert calls == [(snapshot, context.execution, ["author"], "RuntimeError", "claim_safe", "strict", "cmd")]
