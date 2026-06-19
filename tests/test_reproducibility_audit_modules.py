from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext
from paperorchestra.reviews.reproducibility_reasons import build_reproducibility_reasons
from paperorchestra.reviews.reproducibility_report import build_reproducibility_report


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        session_id="session-1",
        latest_runtime_mode="native",
        latest_verify_fallback_used=None,
        latest_provider_name="live-provider",
        latest_verify_mode=None,
        latest_discovery_mode=None,
        notes=[],
        artifacts=SimpleNamespace(
            paper_full_tex="paper.tex",
            citation_registry_json="citation_registry.json",
            citation_map_json="citation_map.json",
            references_bib="references.bib",
            latest_provider_identity_json="provider.json",
            latest_figure_placement_review_json="figure.json",
            latest_runtime_parity_json=None,
            latest_compile_report_json="compile.json",
            latest_prompt_trace_dir="prompts",
            latest_lane_summary_json="lane-summary.json",
        ),
    )


def _context(**overrides) -> ReproducibilityAuditContext:
    defaults = dict(
        state=_state(),
        lane_summary={"manifest_count": 1, "fallback_count": 0, "stages": {}},
        session_artifact_dir=Path("artifacts"),
        runtime_parity={"overall_status": "implemented"},
        provider_identity={"provider": "live"},
        compile_report={"clean": True},
        prompt_trace_dir="prompts",
        prompt_files=[Path("prompts/stage.md")],
        mock_registry_count=0,
        citation_live_provenance={
            "live_verified_count": 1,
            "cited_mock_count": 0,
            "cited_curated_seed_count": 0,
            "seed_only_count": 0,
            "cited_mixed_count": 0,
        },
        citation_support_review_provenance={"semantic_scholar_required": False, "live": True},
        citation_surface={
            "issues": [],
            "registry_entry_count": 1,
            "citation_map_entry_count": 1,
            "references_bib_entry_count": 1,
        },
        validation_warning_reports=[],
        validation_warning_count=0,
        strict_content_gates=False,
        strict_content_gate_issues=[],
        refinement_compile_preservation_count=0,
        verification_invoked=False,
        paper_has_mock_watermark=False,
    )
    defaults.update(overrides)
    return ReproducibilityAuditContext(**defaults)


def test_reproducibility_reasons_classify_blockers_and_warnings() -> None:
    state = _state()
    state.latest_runtime_mode = "omx_native"
    state.latest_verify_fallback_used = "mock"
    state.latest_provider_name = "mock"
    state.latest_verify_mode = "mock"
    context = _context(
        state=state,
        lane_summary={"manifest_count": 0, "fallback_count": 2, "stages": {"verify": {"status": "completed"}}},
        prompt_files=[],
        runtime_parity={"overall_status": "partial"},
        compile_report={"clean": False},
        citation_live_provenance={
            "live_verified_count": 0,
            "cited_mock_count": 1,
            "cited_curated_seed_count": 0,
            "seed_only_count": 0,
            "cited_mixed_count": 0,
        },
        citation_surface={
            "issues": ["citation_registry.json is missing."],
            "registry_entry_count": 0,
            "citation_map_entry_count": 0,
            "references_bib_entry_count": 0,
        },
        validation_warning_count=2,
        refinement_compile_preservation_count=1,
        verification_invoked=True,
        paper_has_mock_watermark=False,
    )

    reasons = build_reproducibility_reasons(context, require_live_verification=False)

    assert reasons.verdict == "BLOCK"
    assert "Prompt trace artifacts are missing; stage prompts cannot be audited after the fact." in reasons.blocking
    assert "OMX-native run used fallback execution in one or more lane manifests." in reasons.blocking
    assert "Live verification fell back to mock verification." in reasons.blocking
    assert "Provider was mock; manuscript output is not a live factual draft." in reasons.blocking
    assert "Citation verification used mock mode." in reasons.blocking
    assert "Cited citation registry contains 1 mock entry/entries." in reasons.blocking
    assert any(reason.startswith("Citation lane completed but final citation artifacts") for reason in reasons.blocking)
    assert "Runtime parity status is partial, not implemented." in reasons.warnings
    assert "Latest compile report is not clean." in reasons.warnings
    assert "No lane manifests were recorded for the current session." in reasons.warnings
    assert "2 non-blocking validation warning(s) were recorded for the current session." in reasons.warnings
    assert any("preserved the prior compiled manuscript" in reason for reason in reasons.warnings)
    assert "Mock or fallback-generated draft is missing the expected manuscript watermark." in reasons.warnings


def test_reproducibility_reasons_enforce_required_live_verification_tail_cases() -> None:
    state = _state()
    state.latest_verify_mode = "live"
    context = _context(
        state=state,
        verification_invoked=True,
        citation_live_provenance={
            "live_verified_count": 0,
            "cited_mock_count": 0,
            "cited_curated_seed_count": 1,
            "seed_only_count": 1,
            "cited_mixed_count": 2,
        },
    )

    reasons = build_reproducibility_reasons(context, require_live_verification=True)

    assert any("1 cited reference is still seed-only" in reason for reason in reasons.blocking)
    assert any("2 cited references have mixed cited provenance" in reason for reason in reasons.blocking)


def test_reproducibility_report_preserves_public_payload_shape() -> None:
    context = _context()
    reasons = build_reproducibility_reasons(context, require_live_verification=False)

    payload = build_reproducibility_report(context, reasons, require_live_verification=False)

    assert payload["session_id"] == "session-1"
    assert payload["verdict"] == "OK"
    assert payload["reasons"] == []
    assert payload["source_artifacts"]["latest_runtime_parity_json"] == "artifacts/runtime-parity.json"
    assert payload["generation_determinism"] == {
        "byte_identical_generation_claimed": False,
        "auditability_claimed": True,
        "rationale": (
            "PaperOrchestra reproducibility audits track inputs, provider/runtime identity, "
            "prompt traces, validation results, and artifact health; they do not promise "
            "byte-identical LLM text generation."
        ),
    }
    assert payload["semantic_scholar_required"] is False
    assert payload["citation_support_review_live"] is True
    assert payload["citation_registry_live_verified_count"] == 1
    assert payload["citation_registry_entry_count"] == 1
    assert payload["paper_has_mock_watermark"] is False


def test_collect_reproducibility_context_uses_runtime_and_prompt_fallbacks(monkeypatch, tmp_path) -> None:
    from paperorchestra.reviews import reproducibility_context

    artifact_dir = tmp_path / "artifacts"
    prompt_dir = artifact_dir / "prompts"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "stage.md"
    prompt_file.write_text("prompt", encoding="utf-8")
    paper = artifact_dir / "paper.tex"
    paper.write_text("paper", encoding="utf-8")
    state = _state()
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.latest_runtime_parity_json = None
    state.artifacts.latest_prompt_trace_dir = None
    state.notes = ["Compile-failed refinement iteration: kept prior"]

    def read_json(path):
        if path and Path(path).name == "runtime-parity.json":
            return {"overall_status": "implemented", "path": str(path)}
        return None

    monkeypatch.setattr(reproducibility_context, "load_session", lambda cwd: state)
    monkeypatch.setattr(reproducibility_context, "build_lane_manifest_summary", lambda cwd: {"manifest_count": 1})
    monkeypatch.setattr(reproducibility_context, "_read_json_if_exists", read_json)
    monkeypatch.setattr(reproducibility_context, "_mock_registry_entry_count", lambda path: 0)
    monkeypatch.setattr(reproducibility_context, "_citation_registry_live_provenance", lambda registry, paper: {"live_verified_count": 0})
    monkeypatch.setattr(reproducibility_context, "_citation_support_review_provenance", lambda cwd, state, session_dir: {"live": False})
    monkeypatch.setattr(
        reproducibility_context,
        "_citation_surface_health",
        lambda state: {"issues": [], "registry_entry_count": 0, "citation_map_entry_count": 0, "references_bib_entry_count": 0},
    )
    monkeypatch.setattr(reproducibility_context, "_validation_warning_reports", lambda state, session_dir: [])
    monkeypatch.setattr(reproducibility_context, "_strict_content_gates_enabled", lambda: False)
    monkeypatch.setattr(reproducibility_context, "_has_mock_watermark", lambda path: False)

    context = reproducibility_context.collect_reproducibility_audit_context("repo")

    assert context.session_artifact_dir == artifact_dir.resolve()
    assert context.runtime_parity == {"overall_status": "implemented", "path": str(artifact_dir / "runtime-parity.json")}
    assert context.prompt_trace_dir == str(artifact_dir.resolve() / "prompts")
    assert context.prompt_files == [prompt_file]
    assert context.refinement_compile_preservation_count == 1


def test_build_reproducibility_audit_composes_context_reasons_and_report(monkeypatch) -> None:
    from paperorchestra.reviews import reproducibility

    context = _context()
    calls = []

    def collect(cwd):
        calls.append(("collect", cwd))
        return context

    def reasons(ctx, *, require_live_verification):
        calls.append(("reasons", ctx is context, require_live_verification))
        return build_reproducibility_reasons(ctx, require_live_verification=require_live_verification)

    def report(ctx, reasons_arg, *, require_live_verification):
        calls.append(("report", ctx is context, reasons_arg.verdict, require_live_verification))
        return {"verdict": reasons_arg.verdict, "require_live_verification": require_live_verification}

    monkeypatch.setattr(reproducibility, "collect_reproducibility_audit_context", collect)
    monkeypatch.setattr(reproducibility, "build_reproducibility_reasons", reasons)
    monkeypatch.setattr(reproducibility, "build_reproducibility_report", report)

    payload = reproducibility.build_reproducibility_audit("repo", require_live_verification=True)

    assert payload == {"verdict": "BLOCK", "require_live_verification": True}
    assert calls == [
        ("collect", "repo"),
        ("reasons", True, True),
        ("report", True, "BLOCK", True),
    ]


def test_reproducibility_reasons_preserves_rule_facade_aliases() -> None:
    from paperorchestra.reviews import reproducibility_blockers, reproducibility_reasons, reproducibility_warnings

    assert reproducibility_reasons.append_artifact_blockers is reproducibility_blockers.append_artifact_blockers
    assert reproducibility_reasons._append_artifact_blockers is reproducibility_blockers.append_artifact_blockers
    assert reproducibility_reasons._append_live_seed_blocker is reproducibility_blockers.append_live_seed_blocker
    assert reproducibility_reasons._append_warnings is reproducibility_warnings.append_warnings
    assert reproducibility_reasons._append_mock_watermark_warning is reproducibility_warnings.append_mock_watermark_warning
