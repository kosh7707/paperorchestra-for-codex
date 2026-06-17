from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError

# Legacy private helper reexports are intentionally kept here while tests and
# downstream scripts still import old refine_stages internals during the
# modularization window. New implementation work should live in focused
# refine_* modules.
from paperorchestra.core.io import ExtractionError, extract_json, extract_latex, read_text, write_json, write_text
from paperorchestra.core.session import artifact_path, load_session, review_path, save_session
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _file_sha256,
    _provider_name,
)
from paperorchestra.engine.latex_postprocess import (
    _ensure_bibliography_hook,
    _ensure_generated_plot_usage,
    _normalize_generated_plot_paths,
    _normalize_source_figure_paths,
    _reviewable_plot_assets_index,
    _reviewable_plot_manifest,
    _stabilize_figure_float_placement,
)
from paperorchestra.engine.planning_stages import (
    _author_facing_writer_brief_block,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _data_block,
    _prompt_compact_text,
    _read_inputs,
    _raise_if_strict_source_citations_unmapped,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
)
from paperorchestra.engine.refine_candidate import (
    RefinementCandidateReview,
    RefinementStateSnapshot,
    review_refinement_candidate,
    snapshot_refinement_state,
)
from paperorchestra.engine.refine_compile import (
    RefinementCompileGateResult,
    apply_compile_acceptance_gate,
    compile_latex,
)
from paperorchestra.engine.refine_context import (
    RefinementIterationContext,
    build_refinement_iteration_context,
)
from paperorchestra.engine.refine_contracts import (
    RefinementContractCheckResult,
    apply_contract_regression_preservation,
)
from paperorchestra.engine.refine_drafts import normalize_refinement_latex, parse_refinement_response
from paperorchestra.engine.refine_iteration import RefinementIterationRun, run_refinement_iteration
from paperorchestra.engine.refine_manifests import (
    record_accepted_refinement_lane_manifest,
    record_rejected_refinement_lane_manifest,
)
from paperorchestra.engine.refine_persistence import (
    apply_accepted_refinement_state,
    apply_candidate_only_refinement_state,
    apply_rejected_refinement_state,
)
from paperorchestra.engine.refine_prompt import build_refinement_user_prompt
from paperorchestra.engine.refine_results import (
    accepted_refinement_result,
    candidate_only_result,
    contract_validation_failed_result,
    rejected_refinement_result,
)
from paperorchestra.engine.reports import _record_validation_report, collect_paper_contract_issues
from paperorchestra.engine.refine_retry import (
    RefinementRetryReviewResult,
    maybe_retry_refinement_review,
)
from paperorchestra.engine.refine_review import (
    _accept_review_delta,
    _redact_review_scores_for_writer,
    should_accept_refinement_candidate,
    should_retry_refinement_review,
)
from paperorchestra.engine.review_stages import _extract_axis_scores, review_current_paper
from paperorchestra.engine.section_scope import _expected_section_titles_from_outline
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.repair import (
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _remove_material_packet_sections,
)
from paperorchestra.manuscript.validator import canonicalize_citation_keys
from paperorchestra.runtime.providers import BaseProvider


def refine_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    iterations: int = 1,
    require_compile_for_accept: bool = False,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    candidate_only: bool = False,
) -> list[dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex or not state.artifacts.latest_review_json:
        raise ContractError("Need paper.full.tex and review.latest.json before refine.")
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)

    accepted_results: list[dict[str, Any]] = []
    for _ in range(iterations):
        run = run_refinement_iteration(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            require_compile_for_accept=require_compile_for_accept,
            candidate_only=candidate_only,
            claim_safe=claim_safe,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
            writer_brief=writer_brief,
        )
        accepted_results.append(run.result)
        if run.stop_after:
            break

    return accepted_results
