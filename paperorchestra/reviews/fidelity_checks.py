from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import SessionState
from paperorchestra.reviews.evaluation import build_generated_citation_titles, build_session_eval_summary
from paperorchestra.reviews.fidelity_citation_partition import ensure_default_citation_partition_request, _citation_partition_scaffold_check
from paperorchestra.reviews.fidelity_eval_checks import (
    _benchmark_surface_check,
    _generated_citation_title_check,
    _review_gate_check,
    _review_gate_comparison_check,
    _search_grounding_check,
)
from paperorchestra.reviews.fidelity_stage_checks import (
    EXPECTED_OUTLINE_KEYS,
    EXPECTED_PROMPT_ASSETS,
    _compile_environment_check,
    _iterative_refinement_check,
    _outline_contract_check,
    _paper_source_check,
    _parallel_semantics_check,
    _plot_generation_check,
    _plot_usage_check,
    _prompt_assets_check,
    _runtime_parity_check,
    _section_writing_check,
    _session_artifact_dir,
    _submission_output_check,
    _verified_citation_lane_check,
)
from paperorchestra.reviews.fidelity_types import FidelityCheck


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
