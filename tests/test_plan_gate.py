from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine import pipeline
from paperorchestra.engine.plan_gate import check_plan_gate, ensure_approved_plan
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class _NoCallProvider(BaseProvider):
    name = "no-call"

    def complete(self, request: CompletionRequest) -> str:  # pragma: no cover - plan gate should stop first
        raise AssertionError("provider must not be called before plan approval")


class _DummyProvider:
    pass


def _approve(path: Path) -> Path:
    path.write_text("# Paper plan\n\n<!-- paperorchestra:plan-approved -->\n", encoding="utf-8")
    return path


def test_plan_gate_reports_missing_plan(tmp_path: Path) -> None:
    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_missing"
    assert result.plan_path is None
    assert "paperorchestra-plan" in result.next_action


def test_plan_gate_blocks_unapproved_plan(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text("# Paper plan\n\nStill under review.\n", encoding="utf-8")

    result = check_plan_gate(tmp_path)

    assert result.allowed is False
    assert result.reason == "paper_plan_unapproved"
    assert result.plan_path == str(tmp_path / "paper-plan.md")
    with pytest.raises(ContractError, match="paper-plan"):
        ensure_approved_plan(tmp_path)


def test_plan_gate_accepts_author_approval_marker(tmp_path: Path) -> None:
    plan_path = _approve(tmp_path / "paper-plan.md")

    result = check_plan_gate(tmp_path)

    assert result.allowed is True
    assert result.reason == "paper_plan_approved"
    assert result.plan_path == str(plan_path)


def test_write_sections_requires_approved_plan_before_loading_session(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="paper-plan"):
        write_sections(tmp_path, _NoCallProvider())

    assert not (tmp_path / ".paper-orchestra").exists()


def test_run_pipeline_returns_blocked_without_touching_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "load_session", lambda cwd: (_ for _ in ()).throw(AssertionError("should not load session")))
    monkeypatch.setattr(pipeline, "generate_outline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not draft")))

    result = pipeline.run_pipeline(tmp_path, provider=_DummyProvider(), verify_mode="mock")

    assert result["status"] == "blocked"
    assert result["reason"] == "paper_plan_missing"
    assert result["plan_gate"]["allowed"] is False


def test_run_pipeline_bypass_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(
        latest_provider_name=None,
        latest_runtime_mode=None,
        latest_verify_mode=None,
        latest_verify_fallback_used=None,
        current_phase=None,
        notes=[],
        artifacts=SimpleNamespace(
            latest_validation_json=None,
            compiled_pdf=None,
            paper_full_tex="/tmp/paper.tex",
            latest_runtime_parity_json=None,
        ),
    )
    monkeypatch.setattr(pipeline, "_provider_name", lambda provider: "dummy-provider")
    monkeypatch.setattr(pipeline, "load_session", lambda cwd: state)
    monkeypatch.setattr(pipeline, "save_session", lambda cwd, saved: None)
    monkeypatch.setattr(pipeline, "record_compile_environment_report", lambda cwd: (tmp_path / "compile-env.json", {}))
    monkeypatch.setattr(pipeline, "generate_outline", lambda *args, **kwargs: tmp_path / "outline.json")
    monkeypatch.setattr(
        pipeline,
        "run_parallel_plot_and_literature",
        lambda *args, **kwargs: {"plots": "", "plot_captions": "", "plot_assets": "", "candidates": ""},
    )
    monkeypatch.setattr(pipeline, "verify_papers", lambda cwd, mode, on_error: tmp_path / "registry.json")
    monkeypatch.setattr(pipeline, "build_bib", lambda cwd: tmp_path / "references.bib")
    monkeypatch.setattr(
        pipeline,
        "plan_narrative_and_claims",
        lambda *args, **kwargs: {
            "narrative_plan": tmp_path / "narrative.json",
            "claim_map": tmp_path / "claims.json",
            "citation_placement_plan": tmp_path / "placements.json",
        },
    )
    monkeypatch.setattr(pipeline, "write_intro_related", lambda *args, **kwargs: tmp_path / "intro.tex")
    monkeypatch.setattr(pipeline, "write_sections", lambda *args, **kwargs: tmp_path / "paper.tex")
    monkeypatch.setattr(pipeline, "review_current_paper", lambda *args, **kwargs: tmp_path / "review.json")
    monkeypatch.setattr(pipeline, "refine_current_paper", lambda *args, **kwargs: [])
    monkeypatch.setattr(pipeline, "record_runtime_parity_report", lambda cwd: (tmp_path / "runtime.json", {}))
    monkeypatch.setattr(pipeline, "record_fidelity_report", lambda cwd: (tmp_path / "fidelity.json", {}))
    monkeypatch.setattr(pipeline, "write_figure_placement_review", lambda cwd: (tmp_path / "figures.json", {}))
    monkeypatch.setattr(pipeline, "write_reproducibility_audit", lambda cwd, require_live_verification: (tmp_path / "repro.json", {}))

    result = pipeline.run_pipeline(
        tmp_path,
        provider=_DummyProvider(),
        verify_mode="mock",
        refine_iterations=0,
        bypass_plan_gate=True,
    )

    assert result["status"] == "draft_complete"
    assert result["plan_gate"]["bypassed"] is True
