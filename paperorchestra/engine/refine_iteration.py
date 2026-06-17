from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json, write_text
from paperorchestra.core.session import artifact_path, load_session, review_path, save_session
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _provider_name
from paperorchestra.engine.latex_postprocess import _drop_unknown_citation_keys
from paperorchestra.engine.prompt_context import _unknown_citation_key_counts
from paperorchestra.engine.refine_candidate import review_refinement_candidate, snapshot_refinement_state
from paperorchestra.engine.refine_compile import apply_compile_acceptance_gate
from paperorchestra.engine.refine_contracts import apply_contract_regression_preservation
from paperorchestra.engine.refine_context import build_refinement_iteration_context
from paperorchestra.engine.refine_drafts import normalize_refinement_latex, parse_refinement_response
from paperorchestra.engine.refine_iteration_outcomes import (
    accepted_iteration_run,
    candidate_only_iteration_run,
    record_refinement_validation_outcome,
    rejected_iteration_run,
)
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
)
from paperorchestra.engine.refine_retry import maybe_retry_refinement_review
from paperorchestra.engine.refine_review import should_accept_refinement_candidate
from paperorchestra.engine.reports import collect_paper_contract_issues
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.providers import BaseProvider


def _prepare_refinement_draft(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    claim_safe: bool,
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    writer_brief: dict[str, Any],
) -> PreparedRefinementDraft:
    state = load_session(cwd)
    iteration = build_refinement_iteration_context(
        cwd,
        state,
        claim_safe=claim_safe,
        writer_brief=writer_brief,
    )
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_refine_system(), user_prompt=iteration.user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="refiner",
        trace_stage="refinement",
    )
    worklog, latex, lane_notes = parse_refinement_response(response, lane_notes=lane_notes)
    latex, citation_replacements = normalize_refinement_latex(
        latex,
        citation_map=iteration.citation_map,
        plot_assets_index=iteration.plot_assets_index,
        figures_dir=state.inputs.figures_dir,
        claim_map=claim_map,
    )
    if iteration.strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, iteration.citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, iteration.citation_map)
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
    validation_issues = collect_paper_contract_issues(
        latex,
        citation_map=iteration.citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=iteration.plot_manifest,
        plot_assets_index=iteration.plot_assets_index,
        experimental_log_text=iteration.experimental_log_text,
        expected_section_titles=iteration.expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    contract_check = apply_contract_regression_preservation(
        cwd=cwd,
        iteration=iteration,
        state=state,
        latex=latex,
        validation_issues=validation_issues,
        worklog=worklog,
        lane_notes=lane_notes,
        citation_map=iteration.citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=iteration.plot_manifest,
        plot_assets_index=iteration.plot_assets_index,
        experimental_log_text=iteration.experimental_log_text,
        expected_section_titles=iteration.expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    lane_notes = _refinement_citation_notes(
        lane_notes=contract_check.lane_notes,
        citation_replacements=citation_replacements,
        dropped_citations=dropped_citations,
        strict_claim_safe_prompt=iteration.strict_claim_safe_prompt,
        has_blocking_issues=bool(contract_check.blocking_issues),
        contract_regression_preservation=contract_check.contract_regression_preservation,
    )
    return PreparedRefinementDraft(
        state=state,
        iteration=iteration,
        latex=contract_check.latex,
        worklog=contract_check.worklog,
        lane_type=lane_type,
        fallback_used=fallback_used,
        lane_notes=lane_notes,
        runtime_mode=runtime_mode,
        validation_issues=contract_check.validation_issues,
        contract_regression_preservation=contract_check.contract_regression_preservation,
    )


def _refinement_citation_notes(
    *,
    lane_notes: list[str],
    citation_replacements: dict[str, str],
    dropped_citations: dict[str, int],
    strict_claim_safe_prompt: bool,
    has_blocking_issues: bool,
    contract_regression_preservation: Any,
) -> list[str]:
    lane_notes = list(lane_notes)
    if not has_blocking_issues and citation_replacements and contract_regression_preservation is None:
        lane_notes.append(
            "Canonicalized citation-key aliases in refinement draft: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
        )
    if dropped_citations:
        note_prefix = (
            "Blocked unsupported citation keys in strict refinement draft: "
            if strict_claim_safe_prompt
            else "Dropped unsupported citation keys in refinement draft: "
        )
        lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))
    return lane_notes


def _write_and_assess_candidate(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    require_compile_for_accept: bool,
    draft: PreparedRefinementDraft,
    validation_path: Path,
    validation_payload: dict[str, Any],
) -> RefinementCandidateAssessment:
    state = draft.state
    iteration = draft.iteration
    candidate_tex_path = artifact_path(cwd, f"paper.refined.iter-{iteration.candidate_iter:02d}.tex")
    worklog_path = review_path(cwd, f"refinement_worklog.iter-{iteration.candidate_iter:02d}.json")
    write_text(candidate_tex_path, draft.latex)
    write_json(worklog_path, draft.worklog)

    candidate_snapshot = snapshot_refinement_state(state, review_payload=iteration.review_payload)
    candidate_review_state = review_refinement_candidate(
        cwd=cwd,
        provider=provider,
        state=state,
        iteration=iteration,
        candidate_tex_path=candidate_tex_path,
        latex=draft.latex,
        runtime_mode=runtime_mode,
        snapshot=candidate_snapshot,
    )
    compile_gate = apply_compile_acceptance_gate(
        enabled=require_compile_for_accept,
        cwd=cwd,
        candidate_iter=iteration.candidate_iter,
        candidate_tex_path=candidate_tex_path,
        latex=draft.latex,
        current_paper=iteration.current_paper,
        previous_review_path=candidate_snapshot.temp_latest_review or state.artifacts.latest_review_json or "",
        previous_score=candidate_snapshot.previous_score,
        previous_axes=candidate_snapshot.previous_axes,
        candidate_review_path=candidate_review_state.candidate_review_path,
        candidate_score=candidate_review_state.candidate_score,
        candidate_axes=candidate_review_state.candidate_axes,
        no_op_refinement=candidate_review_state.no_op_refinement,
        latest_compile_report_json=state.artifacts.latest_compile_report_json,
        compiled_pdf=state.artifacts.compiled_pdf,
        worklog=draft.worklog,
        lane_notes=draft.lane_notes,
    )
    return RefinementCandidateAssessment(
        validation_path=validation_path,
        validation_payload=validation_payload,
        candidate_tex_path=candidate_tex_path,
        worklog_path=worklog_path,
        latex=compile_gate.latex,
        temp_state_paper=candidate_snapshot.temp_state_paper,
        temp_latest_review=candidate_snapshot.temp_latest_review,
        temp_review_history_len=candidate_snapshot.temp_review_history_len,
        previous_score=candidate_snapshot.previous_score,
        previous_axes=candidate_snapshot.previous_axes,
        candidate_review_path=compile_gate.candidate_review_path,
        candidate_score=compile_gate.candidate_score,
        candidate_axes=compile_gate.candidate_axes,
        no_op_refinement=compile_gate.no_op_refinement,
        candidate_pdf_path=compile_gate.candidate_pdf_path,
        compile_error=compile_gate.compile_error,
        compile_preservation=compile_gate.compile_preservation,
        preserved_compile_error=compile_gate.preserved_compile_error,
        worklog=compile_gate.worklog,
        lane_notes=compile_gate.lane_notes,
    )


def _review_refinement_decision(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    iteration: Any,
    assessment: RefinementCandidateAssessment,
) -> RefinementReviewDecision:
    accept = should_accept_refinement_candidate(
        compile_error=assessment.compile_error,
        no_op_refinement=assessment.no_op_refinement,
        candidate_score=assessment.candidate_score,
        previous_score=assessment.previous_score,
        candidate_axes=assessment.candidate_axes,
        previous_axes=assessment.previous_axes,
    )
    retry_review = maybe_retry_refinement_review(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        candidate_iter=iteration.candidate_iter,
        accept=accept,
        no_op_refinement=assessment.no_op_refinement,
        compile_error=assessment.compile_error,
        previous_score=assessment.previous_score,
        candidate_score=assessment.candidate_score,
        previous_axes=assessment.previous_axes,
        candidate_review_path=assessment.candidate_review_path,
    )
    return RefinementReviewDecision(
        accept=retry_review.accept,
        candidate_review_path=retry_review.candidate_review_path,
        candidate_score=retry_review.candidate_score,
        review_retry_paths=retry_review.review_retry_paths,
        review_retry_scores=retry_review.review_retry_scores,
    )


def run_refinement_iteration(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    require_compile_for_accept: bool,
    candidate_only: bool,
    claim_safe: bool,
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    writer_brief: dict[str, Any],
) -> RefinementIterationRun:
    draft = _prepare_refinement_draft(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        claim_safe=claim_safe,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
        writer_brief=writer_brief,
    )
    validation_name = f"validation.refine.iter-{draft.state.refinement_iteration + 1:02d}.json"
    validation_outcome = record_refinement_validation_outcome(
        cwd=cwd,
        state=draft.state,
        iteration=draft.iteration,
        validation_issues=draft.validation_issues,
        validation_name=validation_name,
        latex=draft.latex,
    )
    if validation_outcome.failure_run is not None:
        return validation_outcome.failure_run

    assessment = _write_and_assess_candidate(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        require_compile_for_accept=require_compile_for_accept,
        draft=draft,
        validation_path=validation_outcome.validation_path,
        validation_payload=validation_outcome.validation_payload,
    )
    if candidate_only:
        return candidate_only_iteration_run(
            cwd=cwd,
            iteration=draft.iteration,
            assessment=assessment,
            contract_regression_preservation=draft.contract_regression_preservation,
        )

    decision = _review_refinement_decision(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        iteration=draft.iteration,
        assessment=assessment,
    )
    if decision.accept:
        return accepted_iteration_run(cwd=cwd, draft=draft, assessment=assessment, decision=decision)
    return rejected_iteration_run(cwd=cwd, draft=draft, assessment=assessment, decision=decision)
