from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.manuscript import prompts as prompt_module
from paperorchestra.reviews.fidelity_sources import paper_source_candidates
from paperorchestra.reviews.fidelity_types import FidelityCheck
from paperorchestra.reviews.reproducibility_artifacts import _file_sha256
from paperorchestra.reviews.reproducibility_citations import _citation_surface_health

EXPECTED_OUTLINE_KEYS = {"plotting_plan", "intro_related_work_plan", "section_plan"}
EXPECTED_PROMPT_ASSETS = {
    "outline_agent.md",
    "literature_review_agent.md",
    "section_writing_agent.md",
    "content_refinement_agent.md",
    "prompt_fidelity_matrix.md",
}


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


def _outline_contract_check(state: SessionState) -> FidelityCheck:
    outline_status = "partial"
    if state.artifacts.outline_json and Path(state.artifacts.outline_json).exists():
        outline_payload = read_json(state.artifacts.outline_json)
        outline_status = "implemented" if EXPECTED_OUTLINE_KEYS <= set(outline_payload.keys()) else "missing"
    return FidelityCheck(
        code="outline_json_contract",
        status=outline_status,
        rationale="The paper's Outline Agent emits a structured outline with plotting_plan, intro_related_work_plan, and section_plan.",
    )


def _parallel_semantics_check(state: SessionState) -> FidelityCheck:
    evidence_notes = list(state.notes_archive) + list(state.notes)
    parallel_status = "implemented" if any("completed in parallel" in note.lower() for note in evidence_notes) else "partial"
    return FidelityCheck(
        code="parallel_step_2_3_semantics",
        status=parallel_status,
        rationale="PaperOrchestra runs Plot Generation and Literature Review as sibling parallel stages after outline generation.",
    )


def _verified_citation_lane_check(state: SessionState) -> FidelityCheck:
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


def _plot_generation_check(state: SessionState) -> FidelityCheck:
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


def _plot_usage_check(state: SessionState) -> FidelityCheck:
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


def _section_writing_check(state: SessionState) -> FidelityCheck:
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


def _iterative_refinement_check(state: SessionState) -> FidelityCheck:
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


def _submission_output_check(state: SessionState) -> FidelityCheck:
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


def _compile_environment_check(state: SessionState) -> FidelityCheck:
    compile_env_status = "missing"
    if state.artifacts.latest_compile_env_json and Path(state.artifacts.latest_compile_env_json).exists():
        compile_env_payload = read_json(state.artifacts.latest_compile_env_json)
        compile_env_status = "implemented" if compile_env_payload.get("ready_for_compile") else "partial"
    return FidelityCheck(
        code="compile_environment_ready",
        status=compile_env_status,
        rationale="Submission-ready output requires both a TeX engine and a sandboxed compile wrapper path.",
    )


def _runtime_parity_check(state: SessionState) -> FidelityCheck:
    runtime_parity_status = "missing"
    if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists():
        runtime_parity_payload = read_json(state.artifacts.latest_runtime_parity_json)
        runtime_parity_status = runtime_parity_payload.get("overall_status", "partial")
    return FidelityCheck(
        code="runtime_parity",
        status=runtime_parity_status,
        rationale="A true multi-agent implementation should preserve OMX lane evidence for each paper agent stage.",
    )
