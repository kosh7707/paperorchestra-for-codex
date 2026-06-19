from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.engine import pipeline


class DummyProvider:
    pass


def _state() -> SimpleNamespace:
    return SimpleNamespace(
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


def test_run_pipeline_preserves_stage_order_and_module_patch_surface(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "paper-plan.md").write_text("<!-- paperorchestra:plan-approved -->\n", encoding="utf-8")
    state = _state()
    calls: list[str] = []

    monkeypatch.setattr(pipeline, "_provider_name", lambda provider: "dummy-provider")
    monkeypatch.setattr(pipeline, "load_session", lambda cwd: state)
    monkeypatch.setattr(pipeline, "save_session", lambda cwd, saved: calls.append(f"save:{saved.current_phase}"))
    monkeypatch.setattr(
        pipeline,
        "record_compile_environment_report",
        lambda cwd: (tmp_path / "compile-env.json", {"ok": True}),
    )
    monkeypatch.setattr(pipeline, "generate_outline", lambda cwd, provider, runtime_mode: calls.append("outline") or tmp_path / "outline.json")
    monkeypatch.setattr(
        pipeline,
        "run_parallel_plot_and_literature",
        lambda cwd, provider, discovery_mode, runtime_mode: calls.append("parallel")
        or {
            "plots": "plots.json",
            "plot_captions": "captions.json",
            "plot_assets": "assets.json",
            "candidates": "candidates.json",
        },
    )
    monkeypatch.setattr(pipeline, "verify_papers", lambda cwd, mode, on_error: calls.append(f"verify:{mode}") or tmp_path / "registry.json")
    monkeypatch.setattr(pipeline, "build_bib", lambda cwd: calls.append("bib") or tmp_path / "references.bib")
    monkeypatch.setattr(
        pipeline,
        "plan_narrative_and_claims",
        lambda cwd, provider, runtime_mode: calls.append("narrative")
        or {
            "narrative_plan": tmp_path / "narrative.json",
            "claim_map": tmp_path / "claims.json",
            "citation_placement_plan": tmp_path / "placements.json",
        },
    )

    def intro(cwd, provider, runtime_mode):
        calls.append("intro")
        state.artifacts.latest_validation_json = "intro-validation.json"
        return tmp_path / "intro.tex"

    def sections(cwd, provider, runtime_mode, **kwargs):
        calls.append("sections")
        state.artifacts.latest_validation_json = "section-validation.json"
        return tmp_path / "paper.tex"

    monkeypatch.setattr(pipeline, "write_intro_related", intro)
    monkeypatch.setattr(pipeline, "write_sections", sections)
    monkeypatch.setattr(pipeline, "review_current_paper", lambda cwd, provider, runtime_mode: calls.append("review") or tmp_path / "review.json")
    monkeypatch.setattr(
        pipeline,
        "refine_current_paper",
        lambda cwd, provider, iterations, require_compile_for_accept, runtime_mode: calls.append("refine")
        or [{"accepted": True, "validation_report_path": "refine-validation.json"}],
    )
    monkeypatch.setattr(
        pipeline,
        "record_runtime_parity_report",
        lambda cwd: (tmp_path / "runtime-parity.json", {"status": "ok"}),
    )
    monkeypatch.setattr(
        pipeline,
        "record_fidelity_report",
        lambda cwd: (tmp_path / "fidelity.json", {"status": "ok"}),
    )
    monkeypatch.setattr(
        pipeline,
        "write_figure_placement_review",
        lambda cwd: (tmp_path / "figure-placement.json", {"status": "ok"}),
    )
    monkeypatch.setattr(
        pipeline,
        "write_reproducibility_audit",
        lambda cwd, require_live_verification: (tmp_path / "repro.json", {"verdict": "pass"}),
    )

    result = pipeline.run_pipeline(tmp_path, provider=DummyProvider(), verify_mode="mock", refine_iterations=1)

    assert calls == [
        "save:None",
        "outline",
        "parallel",
        "verify:mock",
        "bib",
        "narrative",
        "intro",
        "sections",
        "review",
        "refine",
        "save:draft_complete",
        "save:draft_complete",
    ]
    assert result["status"] == "draft_complete"
    assert result["validation_reports"] == {
        "intro_related": "intro-validation.json",
        "section_writing": "section-validation.json",
        "refinement": ["refine-validation.json"],
    }
    assert result["figure_placement"] == {"status": "ok"}


def test_run_pipeline_uses_mock_verify_fallback_when_enabled(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "paper-plan.md").write_text("<!-- paperorchestra:plan-approved -->\n", encoding="utf-8")
    state = _state()
    verify_modes: list[str] = []

    def verify(cwd, mode, on_error):
        verify_modes.append(mode)
        if mode == "live":
            raise pipeline.ContractError("live down")
        return tmp_path / "registry.json"

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
    monkeypatch.setattr(pipeline, "verify_papers", verify)
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
        provider=DummyProvider(),
        verify_mode="live",
        verify_fallback_mode="mock",
        refine_iterations=0,
    )

    assert verify_modes == ["live", "mock"]
    assert result["verify_live_error"] == "live down"
    assert result["verify_fallback_used"] == "mock"
    assert state.latest_verify_fallback_used == "mock"
