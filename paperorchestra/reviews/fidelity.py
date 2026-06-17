from __future__ import annotations

import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility import (
    _citation_surface_health,
    _file_sha256,
    _read_json_if_exists,
    build_reproducibility_audit,
    write_reproducibility_audit,
)
from paperorchestra.reviews.evaluation import (
    EXPECTED_LITERATURE_REVIEW_AXES,
    build_generated_citation_titles,
    build_review_gate_comparison,
    build_session_eval_summary,
    write_citation_partition_request,
)
from paperorchestra.core.io import read_json
from paperorchestra.manuscript import prompts as prompt_module
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.validator import canonical_citation_map


@dataclass(frozen=True)
class FidelityCheck:
    code: str
    status: str  # implemented | partial | missing
    rationale: str
    next_step: str | None = None

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


EXPECTED_OUTLINE_KEYS = {"plotting_plan", "intro_related_work_plan", "section_plan"}
PAPER_SOURCE_NAME = "PaperOrchestra A Multi-Agent Framework for Automated AI Research Paper Writing.pdf"
PAPER_SOURCE_ENV_VAR = "PAPERO_REFERENCE_PDF"
def _paper_source_candidates(cwd: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(PAPER_SOURCE_ENV_VAR)
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    if cwd is not None:
        candidates.append(Path(cwd).resolve() / PAPER_SOURCE_NAME)
    repo_root = Path(prompt_module.__file__).resolve().parent.parent
    candidates.append(repo_root / PAPER_SOURCE_NAME)
    return candidates


def _status_histogram(checks: list[FidelityCheck]) -> dict[str, int]:
    counts = Counter(check.status for check in checks)
    return {
        "missing": counts.get("missing", 0),
        "partial": counts.get("partial", 0),
        "implemented": counts.get("implemented", 0),
    }


def _overall_status(checks: list[FidelityCheck]) -> str:
    if not checks:
        return "missing"
    histogram = _status_histogram(checks)
    if histogram["implemented"] == len(checks):
        return "implemented"
    if histogram["missing"] == len(checks):
        return "missing"
    return "partial"


def _summary_descriptor(checks: list[FidelityCheck]) -> str:
    if not checks:
        return "missing"
    histogram = _status_histogram(checks)
    if histogram["implemented"] == len(checks):
        return "complete"
    if histogram["missing"] == len(checks):
        return "missing"
    if histogram["implemented"] >= max(1, len(checks) - 3) and histogram["missing"] <= 2:
        return "mostly_implemented"
    if histogram["implemented"] > 0:
        return "degraded"
    return "partial"


def _ensure_default_citation_partition_request(state, session_artifact_dir: Path | None) -> Path | None:
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


def run_fidelity_audit(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    checks: list[FidelityCheck] = []
    session_artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent if state.artifacts.paper_full_tex else None
    citation_surface = _citation_surface_health(state)

    paper_pdf_present = any(path.exists() for path in _paper_source_candidates(cwd))
    checks.append(
        FidelityCheck(
            code="paper_source_present",
            status="implemented" if paper_pdf_present else "missing",
            rationale="An explicit or locally cached PaperOrchestra reference PDF should remain available as the primary reconstruction reference.",
        )
    )

    prompt_assets_dir = Path(prompt_module.__file__).with_name("prompt_assets")
    prompt_asset_status = "missing"
    expected_prompt_assets = {
        "outline_agent.md",
        "literature_review_agent.md",
        "section_writing_agent.md",
        "content_refinement_agent.md",
        "prompt_fidelity_matrix.md",
    }
    if prompt_assets_dir.exists():
        present_assets = {path.name for path in prompt_assets_dir.iterdir() if path.is_file()}
        if expected_prompt_assets <= present_assets:
            prompt_asset_status = "implemented"
        elif present_assets:
            prompt_asset_status = "partial"
    checks.append(
        FidelityCheck(
            code="appendix_f_prompt_fidelity_assets",
            status=prompt_asset_status,
            rationale="Prompt fidelity claims should be backed by first-class Appendix F-derived prompt assets, not only compressed inline prompt summaries.",
        )
    )

    outline_status = "partial"
    if state.artifacts.outline_json and Path(state.artifacts.outline_json).exists():
        outline_payload = read_json(state.artifacts.outline_json)
        outline_status = "implemented" if EXPECTED_OUTLINE_KEYS <= set(outline_payload.keys()) else "missing"
    checks.append(
        FidelityCheck(
            code="outline_json_contract",
            status=outline_status,
            rationale="The paper's Outline Agent emits a structured outline with plotting_plan, intro_related_work_plan, and section_plan.",
        )
    )

    evidence_notes = list(state.notes_archive) + list(state.notes)
    parallel_status = "implemented" if any("completed in parallel" in note.lower() for note in evidence_notes) else "partial"
    checks.append(
        FidelityCheck(
            code="parallel_step_2_3_semantics",
            status=parallel_status,
            rationale="PaperOrchestra runs Plot Generation and Literature Review as sibling parallel stages after outline generation.",
        )
    )

    citation_status = citation_surface["status"]
    checks.append(
        FidelityCheck(
            code="verified_citation_lane",
            status=citation_status,
            rationale="The paper requires candidate discovery, verification, citation registry construction, and BibTeX generation.",
            next_step=(
                "Rebuild the citation lane and confirm citation_registry.json, citation_map.json, and references.bib are non-empty."
                if citation_surface["issues"]
                else None
            ),
        )
    )

    plot_status = "missing"
    if state.artifacts.plot_manifest_json and state.artifacts.plot_captions_json:
        plot_status = "partial"
        if state.artifacts.plot_assets_json and Path(state.artifacts.plot_assets_json).exists():
            try:
                assets_payload = read_json(state.artifacts.plot_assets_json)
                assets = assets_payload.get("assets", [])
                if assets:
                    plot_status = "implemented"
            except Exception:
                plot_status = "partial"
        elif state.inputs.figures_dir and Path(state.inputs.figures_dir).exists() and any(Path(state.inputs.figures_dir).iterdir()):
            plot_status = "implemented"
    checks.append(
        FidelityCheck(
            code="plot_generation_depth",
            status=plot_status,
            rationale="The paper includes a dedicated Plot Generation stage with visual artifacts and captions, not only planning text.",
        )
    )

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
    checks.append(
        FidelityCheck(
            code="generated_plot_assets_used_in_manuscript",
            status=plot_usage_status,
            rationale="Generated plot assets should be referenced directly in the manuscript, not only stored as side artifacts.",
        )
    )

    writing_status = "missing"
    if state.artifacts.intro_related_tex and state.artifacts.paper_full_tex:
        writing_status = "implemented"
    elif state.artifacts.paper_full_tex:
        writing_status = "partial"
    checks.append(
        FidelityCheck(
            code="section_writing_pipeline",
            status=writing_status,
            rationale="The paper first drafts Introduction/Related Work from verified citations and then completes the remaining sections.",
        )
    )

    refinement_status = "missing"
    if state.review_history:
        refinement_status = "partial"
        if state.refinement_iteration > 0:
            refinement_status = "implemented"
    checks.append(
        FidelityCheck(
            code="iterative_refinement_gate",
            status=refinement_status,
            rationale="The paper's refinement loop accepts revisions only on non-regressive review outcomes.",
        )
    )

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
    checks.append(
        FidelityCheck(
            code="submission_ready_output",
            status=submission_status,
            rationale="The paper's final output is a LaTeX manuscript plus compiled PDF; draft-only output is partial fidelity.",
        )
    )

    compile_env_status = "missing"
    if state.artifacts.latest_compile_env_json and Path(state.artifacts.latest_compile_env_json).exists():
        compile_env_payload = read_json(state.artifacts.latest_compile_env_json)
        compile_env_status = "implemented" if compile_env_payload.get("ready_for_compile") else "partial"
    checks.append(
        FidelityCheck(
            code="compile_environment_ready",
            status=compile_env_status,
            rationale="Submission-ready output requires both a TeX engine and a sandboxed compile wrapper path.",
        )
    )

    runtime_parity_status = "missing"
    if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists():
        runtime_parity_payload = read_json(state.artifacts.latest_runtime_parity_json)
        runtime_parity_status = runtime_parity_payload.get("overall_status", "partial")
    checks.append(
        FidelityCheck(
            code="runtime_parity",
            status=runtime_parity_status,
            rationale="A true multi-agent implementation should preserve OMX lane evidence for each paper agent stage.",
        )
    )

    eval_summary = build_session_eval_summary(cwd)
    review_axes = eval_summary.get("review_axis_scores") or {}
    available_axes = set(review_axes) if isinstance(review_axes, dict) else set()
    review_gate_status = "missing"
    if eval_summary.get("review_overall_score") is not None:
        review_gate_status = "partial"
        if set(EXPECTED_LITERATURE_REVIEW_AXES) <= available_axes:
            review_gate_status = "implemented"
    checks.append(
        FidelityCheck(
            code="agentreview_substitute_surface",
            status=review_gate_status,
            rationale="The GPT/Codex port should expose a review-gate surface comparable to the paper's structured literature-review autorater axes.",
        )
    )

    review_gate_comparison_status = "missing"
    if state.artifacts.paper_full_tex:
        session_artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent
        review_gate_path = session_artifact_dir / "review_gate_comparison.json"
        if review_gate_path.exists():
            review_gate_payload = read_json(review_gate_path)
            review_gate_comparison_status = review_gate_payload.get("comparability_status", "partial")
        else:
            review_gate_payload = build_review_gate_comparison(cwd)
            review_gate_comparison_status = review_gate_payload.get("comparability_status", "partial")
    checks.append(
        FidelityCheck(
            code="review_gate_comparison_surface",
            status=review_gate_comparison_status,
            rationale="Benchmark/eval proof should include a dedicated artifact comparing the current review output against the expected AgentReview-style surface.",
        )
    )

    search_grounding_status = "missing"
    discovery_sources = eval_summary.get("candidate_discovery_sources") or []
    attempted_sources = eval_summary.get("candidate_discovery_attempted_sources") or []
    if discovery_sources or attempted_sources:
        search_grounding_status = "partial"
        if eval_summary.get("search_grounded_attempted_required_sources_present") or {"semantic_scholar", "openalex"} <= set(discovery_sources):
            search_grounding_status = "implemented"
    checks.append(
        FidelityCheck(
            code="search_grounding_substitute_surface",
            status=search_grounding_status,
            rationale="The GPT/Codex port should provide an explicit bounded substitute for the paper's search-grounded literature discovery rather than relying only on unguided title guessing.",
        )
    )

    benchmark_surface_status = "missing"
    if session_artifact_dir:
        session_eval_summary_path = session_artifact_dir / "session_eval_summary.json"
        reference_comparison_path = session_artifact_dir / "reference_comparison.json"
        if session_eval_summary_path.exists():
            benchmark_surface_status = "partial"
        if session_eval_summary_path.exists() and reference_comparison_path.exists():
            benchmark_surface_status = "implemented"
    checks.append(
        FidelityCheck(
            code="benchmark_eval_surface",
            status=benchmark_surface_status,
            rationale="Reconstruction claims should be backed by benchmark/eval artifacts that package a reference case, summarize the current session, and compare the two surfaces.",
        )
    )

    generated_citation_status = "missing"
    generated_citations = build_generated_citation_titles(cwd)
    if generated_citations.get("count", 0) > 0 and state.artifacts.citation_map_json:
        generated_citation_status = "partial"
        session_artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent if state.artifacts.paper_full_tex else None
        generated_titles_path = session_artifact_dir / "generated_citation_titles.json" if session_artifact_dir else None
        if generated_titles_path and generated_titles_path.exists():
            generated_payload = read_json(generated_titles_path)
            if generated_payload.get("count", 0) > 0 and generated_payload.get("resolved_entries"):
                generated_citation_status = "implemented"
    checks.append(
        FidelityCheck(
            code="generated_citation_title_surface",
            status=generated_citation_status,
            rationale="Eval proof should include an artifact that resolves the generated paper's cite keys into comparable citation titles.",
        )
    )

    partition_scaffold_status = "missing"
    if state.artifacts.paper_full_tex and session_artifact_dir is not None:
        _ensure_default_citation_partition_request(state, session_artifact_dir)
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
    checks.append(
        FidelityCheck(
            code="citation_partition_scaffold_surface",
            status=partition_scaffold_status,
            rationale="Benchmark/eval proof should include a partition-based citation coverage scaffold tying generated citations back to a reference-case P0/P1-style split.",
            next_step=(
                "Run `paperorchestra quality-gate --no-fail-on-block` after adding partitioned coverage evidence to the session artifacts."
                if partition_scaffold_status != "implemented"
                else None
            ),
        )
    )

    histogram = _status_histogram(checks)
    return {
        "session_id": state.session_id,
        "overall_status": _overall_status(checks),
        "status_histogram": histogram,
        "summary_descriptor": _summary_descriptor(checks),
        "checks": [check.to_dict() for check in checks],
    }
