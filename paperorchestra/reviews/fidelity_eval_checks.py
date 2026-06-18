from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.reviews.evaluation import EXPECTED_LITERATURE_REVIEW_AXES, build_review_gate_comparison
from paperorchestra.reviews.fidelity_types import FidelityCheck


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


def _review_gate_comparison_check(cwd: str | Path | None, state: SessionState, session_artifact_dir: Path | None) -> FidelityCheck:
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


def _generated_citation_title_check(state: SessionState, generated_citations: dict[str, Any], session_artifact_dir: Path | None) -> FidelityCheck:
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
