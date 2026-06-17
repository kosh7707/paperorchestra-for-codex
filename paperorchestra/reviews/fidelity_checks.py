from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.manuscript import prompts as prompt_module
from paperorchestra.reviews.evaluation import (
    EXPECTED_LITERATURE_REVIEW_AXES,
    build_generated_citation_titles,
    build_review_gate_comparison,
    build_session_eval_summary,
    write_citation_partition_request,
)
from paperorchestra.manuscript.validator import canonical_citation_map
from paperorchestra.reviews.fidelity_sources import paper_source_candidates
from paperorchestra.reviews.fidelity_types import FidelityCheck
from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.reproducibility_citations import _citation_surface_health

EXPECTED_OUTLINE_KEYS = {"plotting_plan", "intro_related_work_plan", "section_plan"}
EXPECTED_PROMPT_ASSETS = {
    "outline_agent.md",
    "literature_review_agent.md",
    "section_writing_agent.md",
    "content_refinement_agent.md",
    "prompt_fidelity_matrix.md",
}


def build_fidelity_checks(cwd: str | Path | None, state: SessionState) -> list[FidelityCheck]:
    session_artifact_dir = _session_artifact_dir(state)
    checks = [
        _paper_source_check(cwd),
        _prompt_assets_check(),
        _outline_contract_check(state),
        _parallel_semantics_check(state),
        _verified_citation_lane_check(state),
        _plot_generation_check(state),
        _plot_usage_check(state),
        _section_writing_check(state),
        _iterative_refinement_check(state),
        _submission_output_check(state),
        _compile_environment_check(state),
        _runtime_parity_check(state),
    ]

    eval_summary = build_session_eval_summary(cwd)
    checks.extend(
        [
            _review_gate_check(eval_summary),
            _review_gate_comparison_check(cwd, state, session_artifact_dir),
            _search_grounding_check(eval_summary),
            _benchmark_surface_check(session_artifact_dir),
        ]
    )

    generated_citations = build_generated_citation_titles(cwd)
    checks.extend(
        [
            _generated_citation_title_check(state, generated_citations, session_artifact_dir),
            _citation_partition_scaffold_check(state, session_artifact_dir),
        ]
    )
    return checks


def _session_artifact_dir(state: SessionState) -> Path | None:
    if not state.artifacts.paper_full_tex:
        return None
    return Path(state.artifacts.paper_full_tex).resolve().parent


def _paper_source_check(cwd: str | Path | None) -> FidelityCheck:
    return FidelityCheck(
        code="paper_source_present",
        status="implemented" if any(path.exists() for path in paper_source_candidates(cwd)) else "missing",
        rationale="An explicit or locally cached PaperOrchestra reference PDF should remain available as the primary reconstruction reference.",
    )


def _prompt_assets_check() -> FidelityCheck:
    prompt_assets_dir = Path(prompt_module.__file__).with_name("prompt_assets")
    prompt_asset_status = "missing"
    if prompt_assets_dir.exists():
        present_assets = {path.name for path in prompt_assets_dir.iterdir() if path.is_file()}
        if EXPECTED_PROMPT_ASSETS <= present_assets:
            prompt_asset_status = "implemented"
        elif present_assets:
            prompt_asset_status = "partial"
    return FidelityCheck(
        code="appendix_f_prompt_fidelity_assets",
        status=prompt_asset_status,
        rationale="Prompt fidelity claims should be backed by first-class Appendix F-derived prompt assets, not only compressed inline prompt summaries.",
    )


def _outline_contract_check(state) -> FidelityCheck:
    outline_status = "partial"
    if state.artifacts.outline_json and Path(state.artifacts.outline_json).exists():
        outline_payload = read_json(state.artifacts.outline_json)
        outline_status = "implemented" if EXPECTED_OUTLINE_KEYS <= set(outline_payload.keys()) else "missing"
    return FidelityCheck(
        code="outline_json_contract",
        status=outline_status,
        rationale="The paper's Outline Agent emits a structured outline with plotting_plan, intro_related_work_plan, and section_plan.",
    )


def _parallel_semantics_check(state) -> FidelityCheck:
    evidence_notes = list(state.notes_archive) + list(state.notes)
    parallel_status = "implemented" if any("completed in parallel" in note.lower() for note in evidence_notes) else "partial"
    return FidelityCheck(
        code="parallel_step_2_3_semantics",
        status=parallel_status,
        rationale="PaperOrchestra runs Plot Generation and Literature Review as sibling parallel stages after outline generation.",
    )


def _verified_citation_lane_check(state) -> FidelityCheck:
    citation_surface = _citation_surface_health(state)
    return FidelityCheck(
        code="verified_citation_lane",
        status=citation_surface["status"],
        rationale="The paper requires candidate discovery, verification, citation registry construction, and BibTeX generation.",
        next_step=(
            "Rebuild the citation lane and confirm citation_registry.json, citation_map.json, and references.bib are non-empty."
            if citation_surface["issues"]
            else None
        ),
    )


def _plot_generation_check(state) -> FidelityCheck:
    plot_status = "missing"
    if state.artifacts.plot_manifest_json and state.artifacts.plot_captions_json:
        plot_status = "partial"
        if state.artifacts.plot_assets_json and Path(state.artifacts.plot_assets_json).exists():
            try:
                assets_payload = read_json(state.artifacts.plot_assets_json)
                if assets_payload.get("assets", []):
                    plot_status = "implemented"
            except Exception:
                plot_status = "partial"
        elif state.inputs.figures_dir and Path(state.inputs.figures_dir).exists() and any(Path(state.inputs.figures_dir).iterdir()):
            plot_status = "implemented"
    return FidelityCheck(
        code="plot_generation_depth",
        status=plot_status,
        rationale="The paper includes a dedicated Plot Generation stage with visual artifacts and captions, not only planning text.",
    )


def _plot_usage_check(state) -> FidelityCheck:
    plot_usage_status = "missing"
    if state.artifacts.plot_assets_json and Path(state.artifacts.plot_assets_json).exists() and state.artifacts.paper_full_tex:
        plot_usage_status = "partial"
        try:
            assets_payload = read_json(state.artifacts.plot_assets_json)
            latex_text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
            asset_references = [
                asset.get("latex_snippet_path") or asset.get("latex_path") or asset.get("filename")
                for asset in assets_payload.get("assets", [])
                if isinstance(asset, dict) and isinstance(asset.get("filename"), str)
            ]
            if asset_references and all(reference in latex_text for reference in asset_references):
                plot_usage_status = "implemented"
        except Exception:
            plot_usage_status = "partial"
    return FidelityCheck(
        code="generated_plot_assets_used_in_manuscript",
        status=plot_usage_status,
        rationale="Generated plot assets should be referenced directly in the manuscript, not only stored as side artifacts.",
    )


def _section_writing_check(state) -> FidelityCheck:
    writing_status = "missing"
    if state.artifacts.intro_related_tex and state.artifacts.paper_full_tex:
        writing_status = "implemented"
    elif state.artifacts.paper_full_tex:
        writing_status = "partial"
    return FidelityCheck(
        code="section_writing_pipeline",
        status=writing_status,
        rationale="The paper first drafts Introduction/Related Work from verified citations and then completes the remaining sections.",
    )


def _iterative_refinement_check(state) -> FidelityCheck:
    refinement_status = "missing"
    if state.review_history:
        refinement_status = "partial"
        if state.refinement_iteration > 0:
            refinement_status = "implemented"
    return FidelityCheck(
        code="iterative_refinement_gate",
        status=refinement_status,
        rationale="The paper's refinement loop accepts revisions only on non-regressive review outcomes.",
    )


def _submission_output_check(state) -> FidelityCheck:
    submission_status = "partial"
    if state.artifacts.latest_compile_report_json and Path(state.artifacts.latest_compile_report_json).exists():
        compile_report = read_json(state.artifacts.latest_compile_report_json)
        current_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
        current_pdf_sha = _file_sha256(compile_report.get("pdf_path"))
        compile_report_current = (
            bool(current_manuscript_sha)
            and compile_report.get("manuscript_sha256") == current_manuscript_sha
            and bool(current_pdf_sha)
            and (not compile_report.get("pdf_sha256") or compile_report.get("pdf_sha256") == current_pdf_sha)
        )
        if compile_report.get("clean") and compile_report.get("pdf_exists") and compile_report_current:
            submission_status = "implemented"
        elif compile_report.get("pdf_exists"):
            submission_status = "partial"
    elif state.artifacts.compiled_pdf:
        submission_status = "implemented"
    return FidelityCheck(
        code="submission_ready_output",
        status=submission_status,
        rationale="The paper's final output is a LaTeX manuscript plus compiled PDF; draft-only output is partial fidelity.",
    )


def _compile_environment_check(state) -> FidelityCheck:
    compile_env_status = "missing"
    if state.artifacts.latest_compile_env_json and Path(state.artifacts.latest_compile_env_json).exists():
        compile_env_payload = read_json(state.artifacts.latest_compile_env_json)
        compile_env_status = "implemented" if compile_env_payload.get("ready_for_compile") else "partial"
    return FidelityCheck(
        code="compile_environment_ready",
        status=compile_env_status,
        rationale="Submission-ready output requires both a TeX engine and a sandboxed compile wrapper path.",
    )


def _runtime_parity_check(state) -> FidelityCheck:
    runtime_parity_status = "missing"
    if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists():
        runtime_parity_payload = read_json(state.artifacts.latest_runtime_parity_json)
        runtime_parity_status = runtime_parity_payload.get("overall_status", "partial")
    return FidelityCheck(
        code="runtime_parity",
        status=runtime_parity_status,
        rationale="A true multi-agent implementation should preserve OMX lane evidence for each paper agent stage.",
    )


def _review_gate_check(eval_summary: dict[str, Any]) -> FidelityCheck:
    review_axes = eval_summary.get("review_axis_scores") or {}
    available_axes = set(review_axes) if isinstance(review_axes, dict) else set()
    review_gate_status = "missing"
    if eval_summary.get("review_overall_score") is not None:
        review_gate_status = "partial"
        if set(EXPECTED_LITERATURE_REVIEW_AXES) <= available_axes:
            review_gate_status = "implemented"
    return FidelityCheck(
        code="agentreview_substitute_surface",
        status=review_gate_status,
        rationale="The GPT/Codex port should expose a review-gate surface comparable to the paper's structured literature-review autorater axes.",
    )


def _review_gate_comparison_check(cwd: str | Path | None, state, session_artifact_dir: Path | None) -> FidelityCheck:
    review_gate_comparison_status = "missing"
    if state.artifacts.paper_full_tex and session_artifact_dir is not None:
        review_gate_path = session_artifact_dir / "review_gate_comparison.json"
        if review_gate_path.exists():
            review_gate_payload = read_json(review_gate_path)
            review_gate_comparison_status = review_gate_payload.get("comparability_status", "partial")
        else:
            review_gate_payload = build_review_gate_comparison(cwd)
            review_gate_comparison_status = review_gate_payload.get("comparability_status", "partial")
    return FidelityCheck(
        code="review_gate_comparison_surface",
        status=review_gate_comparison_status,
        rationale="Benchmark/eval proof should include a dedicated artifact comparing the current review output against the expected AgentReview-style surface.",
    )


def _search_grounding_check(eval_summary: dict[str, Any]) -> FidelityCheck:
    search_grounding_status = "missing"
    discovery_sources = eval_summary.get("candidate_discovery_sources") or []
    attempted_sources = eval_summary.get("candidate_discovery_attempted_sources") or []
    if discovery_sources or attempted_sources:
        search_grounding_status = "partial"
        if eval_summary.get("search_grounded_attempted_required_sources_present") or {"semantic_scholar", "openalex"} <= set(discovery_sources):
            search_grounding_status = "implemented"
    return FidelityCheck(
        code="search_grounding_substitute_surface",
        status=search_grounding_status,
        rationale="The GPT/Codex port should provide an explicit bounded substitute for the paper's search-grounded literature discovery rather than relying only on unguided title guessing.",
    )


def _benchmark_surface_check(session_artifact_dir: Path | None) -> FidelityCheck:
    benchmark_surface_status = "missing"
    if session_artifact_dir:
        session_eval_summary_path = session_artifact_dir / "session_eval_summary.json"
        reference_comparison_path = session_artifact_dir / "reference_comparison.json"
        if session_eval_summary_path.exists():
            benchmark_surface_status = "partial"
        if session_eval_summary_path.exists() and reference_comparison_path.exists():
            benchmark_surface_status = "implemented"
    return FidelityCheck(
        code="benchmark_eval_surface",
        status=benchmark_surface_status,
        rationale="Reconstruction claims should be backed by benchmark/eval artifacts that package a reference case, summarize the current session, and compare the two surfaces.",
    )


def _generated_citation_title_check(state, generated_citations: dict[str, Any], session_artifact_dir: Path | None) -> FidelityCheck:
    generated_citation_status = "missing"
    if generated_citations.get("count", 0) > 0 and state.artifacts.citation_map_json:
        generated_citation_status = "partial"
        generated_titles_path = session_artifact_dir / "generated_citation_titles.json" if session_artifact_dir else None
        if generated_titles_path and generated_titles_path.exists():
            generated_payload = read_json(generated_titles_path)
            if generated_payload.get("count", 0) > 0 and generated_payload.get("resolved_entries"):
                generated_citation_status = "implemented"
    return FidelityCheck(
        code="generated_citation_title_surface",
        status=generated_citation_status,
        rationale="Eval proof should include an artifact that resolves the generated paper's cite keys into comparable citation titles.",
    )


def ensure_default_citation_partition_request(state: SessionState, session_artifact_dir: Path | None) -> Path | None:
    if session_artifact_dir is None or not state.artifacts.paper_full_tex or not state.artifacts.citation_map_json:
        return None
    output_path = session_artifact_dir / "citation_partition_request.json"
    if output_path.exists():
        return output_path
    citation_map = _read_json_if_exists(state.artifacts.citation_map_json)
    if not isinstance(citation_map, dict) or not citation_map:
        return None
    references = [
        {"title": entry.get("title"), "citation_key": key}
        for key, entry in canonical_citation_map(citation_map).items()
        if isinstance(entry, dict) and isinstance(entry.get("title"), str) and entry.get("title", "").strip()
    ]
    if not references:
        return None
    paper_text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    return write_citation_partition_request(paper_text, references, output_path)


def _citation_partition_scaffold_check(state: SessionState, session_artifact_dir: Path | None) -> FidelityCheck:
    partition_scaffold_status = "missing"
    if state.artifacts.paper_full_tex and session_artifact_dir is not None:
        ensure_default_citation_partition_request(state, session_artifact_dir)
        partition_request = session_artifact_dir / "citation_partition_request.json"
        if partition_request.exists():
            partition_request_payload = read_json(partition_request)
            if partition_request_payload.get("reference_count", 0) > 0:
                partition_scaffold_status = "partial"
        partition_artifact = session_artifact_dir / "reference_case_partitioned_citation_coverage.json"
        if partition_artifact.exists():
            partition_payload = read_json(partition_artifact)
            if partition_payload.get("coverage", {}).get("partition_coverage"):
                partition_scaffold_status = "implemented"
            else:
                partition_scaffold_status = "partial"
    return FidelityCheck(
        code="citation_partition_scaffold_surface",
        status=partition_scaffold_status,
        rationale="Benchmark/eval proof should include a partition-based citation coverage scaffold tying generated citations back to a reference-case P0/P1-style split.",
        next_step=(
            "Run `paperorchestra quality-gate --no-fail-on-block` after adding partitioned coverage evidence to the session artifacts."
            if partition_scaffold_status != "implemented"
            else None
        ),
    )
