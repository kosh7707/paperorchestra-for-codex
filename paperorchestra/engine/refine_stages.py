from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import ExtractionError, extract_json, extract_latex, read_text, write_json, write_text
from paperorchestra.core.session import artifact_path, load_session, review_path, save_session
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _file_sha256,
    _provider_name,
)
from paperorchestra.engine.latex_postprocess import (
    _drop_unknown_citation_keys,
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
from paperorchestra.engine.refine_prompt import build_refinement_user_prompt
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _data_block,
    _prompt_compact_text,
    _read_inputs,
    _raise_if_strict_source_citations_unmapped,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
    _unknown_citation_key_counts,
)
from paperorchestra.engine.reports import (
    _blocking_issues,
    _issue_messages,
    _record_validation_report,
    collect_paper_contract_issues,
)
from paperorchestra.engine.refine_context import (
    RefinementIterationContext,
    build_refinement_iteration_context,
)
from paperorchestra.engine.refine_compile import (
    RefinementCompileGateResult,
    apply_compile_acceptance_gate,
    compile_latex,
)
from paperorchestra.engine.refine_candidate import (
    RefinementCandidateReview,
    RefinementStateSnapshot,
    review_refinement_candidate,
    snapshot_refinement_state,
)
from paperorchestra.engine.refine_drafts import normalize_refinement_latex, parse_refinement_response
from paperorchestra.engine.refine_results import (
    accepted_refinement_result,
    candidate_only_result,
    contract_validation_failed_result,
    rejected_refinement_result,
)
from paperorchestra.engine.refine_manifests import (
    record_accepted_refinement_lane_manifest,
    record_rejected_refinement_lane_manifest,
)
from paperorchestra.engine.refine_persistence import (
    apply_accepted_refinement_state,
    apply_candidate_only_refinement_state,
    apply_rejected_refinement_state,
)
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
        blocking_issues = _blocking_issues(validation_issues)
        contract_regression_preservation: dict[str, Any] | None = None
        if blocking_issues:
            preserved_issues = collect_paper_contract_issues(
                iteration.current_paper,
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
            if not _blocking_issues(preserved_issues):
                rejected_candidate_path = artifact_path(cwd, f"paper.refined.iter-{iteration.candidate_iter:02d}.rejected-contract.tex")
                write_text(rejected_candidate_path, latex)
                rejected_validation_path, _rejected_validation_payload = _record_validation_report(
                    cwd,
                    stage="refinement_rejected_contract_regression",
                    issues=validation_issues,
                    name=f"validation.refine.iter-{iteration.candidate_iter:02d}.rejected-contract.json",
                    manuscript_text=latex,
                )
                contract_regression_preservation = {
                    "preserved_prior_after_contract_regression": True,
                    "rejected_candidate_path": str(rejected_candidate_path),
                    "rejected_candidate_sha256": _file_sha256(rejected_candidate_path),
                    "contract_regression_issue_count": len(_blocking_issues(validation_issues)),
                    "contract_regression_validation_report_path": str(rejected_validation_path),
                }
                latex = iteration.current_paper
                validation_issues = preserved_issues
                blocking_issues = []
                worklog.setdefault("actions_taken", []).append(
                    "Preserved the pre-refinement manuscript because the generated revision regressed citation/grounding contract checks."
                )
                lane_notes = lane_notes + ["Refinement draft regressed contract checks; preserved prior validated manuscript."]
                print(
                    f"Refinement iter {state.refinement_iteration + 1} preserved prior manuscript after contract regression.",
                    file=sys.stderr,
                )
        elif citation_replacements:
            lane_notes.append(
                "Canonicalized citation-key aliases in refinement draft: "
                + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
            )
        if dropped_citations:
            note_prefix = (
                "Blocked unsupported citation keys in strict refinement draft: "
                if iteration.strict_claim_safe_prompt
                else "Dropped unsupported citation keys in refinement draft: "
            )
            lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

        validation_name = f"validation.refine.iter-{state.refinement_iteration + 1:02d}.json"
        validation_path, validation_payload = _record_validation_report(
            cwd,
            stage="refinement",
            issues=validation_issues,
            name=validation_name,
            manuscript_text=latex,
        )
        state.artifacts.latest_validation_json = str(validation_path)
        blocking_issues = _blocking_issues(validation_issues)
        if blocking_issues:
            accepted_results.append(
                contract_validation_failed_result(
                    iteration=state.refinement_iteration + 1,
                    score_before=state.review_history[-1].overall_score if state.review_history else float(iteration.review_payload.get("overall_score", 0.0)),
                    paper_path=state.artifacts.paper_full_tex,
                    issues=_issue_messages(blocking_issues),
                    validation_path=validation_path,
                    validation_payload=validation_payload,
                )
            )
            state.notes.append(
                f"Rejected refinement iteration {state.refinement_iteration + 1} due to contract validation failure."
            )
            print(
                f"Refinement iter {state.refinement_iteration + 1} rejected: contract validation failed ({'; '.join(_issue_messages(blocking_issues))})",
                file=sys.stderr,
            )
            save_session(cwd, state)
            break
        if validation_issues:
            state.notes.append(
                f"Refinement iteration {state.refinement_iteration + 1} produced validation warnings: "
                + " | ".join(_issue_messages(validation_issues))
            )

        candidate_tex_path = artifact_path(cwd, f"paper.refined.iter-{iteration.candidate_iter:02d}.tex")
        worklog_path = review_path(cwd, f"refinement_worklog.iter-{iteration.candidate_iter:02d}.json")
        write_text(candidate_tex_path, latex)
        write_json(worklog_path, worklog)

        candidate_snapshot = snapshot_refinement_state(state, review_payload=iteration.review_payload)
        temp_state_paper = candidate_snapshot.temp_state_paper
        temp_latest_review = candidate_snapshot.temp_latest_review
        temp_review_history_len = candidate_snapshot.temp_review_history_len
        previous_score = candidate_snapshot.previous_score
        previous_axes = candidate_snapshot.previous_axes
        candidate_review_state = review_refinement_candidate(
            cwd=cwd,
            provider=provider,
            state=state,
            iteration=iteration,
            candidate_tex_path=candidate_tex_path,
            latex=latex,
            runtime_mode=runtime_mode,
            snapshot=candidate_snapshot,
        )
        candidate_review_path = candidate_review_state.candidate_review_path
        candidate_score = candidate_review_state.candidate_score
        candidate_axes = candidate_review_state.candidate_axes
        no_op_refinement = candidate_review_state.no_op_refinement
        compile_gate = apply_compile_acceptance_gate(
            enabled=require_compile_for_accept,
            cwd=cwd,
            candidate_iter=iteration.candidate_iter,
            candidate_tex_path=candidate_tex_path,
            latex=latex,
            current_paper=iteration.current_paper,
            previous_review_path=temp_latest_review or state.artifacts.latest_review_json or "",
            previous_score=previous_score,
            previous_axes=previous_axes,
            candidate_review_path=candidate_review_path,
            candidate_score=candidate_score,
            candidate_axes=candidate_axes,
            no_op_refinement=no_op_refinement,
            latest_compile_report_json=state.artifacts.latest_compile_report_json,
            compiled_pdf=state.artifacts.compiled_pdf,
            worklog=worklog,
            lane_notes=lane_notes,
        )
        latex = compile_gate.latex
        candidate_pdf_path = compile_gate.candidate_pdf_path
        compile_error = compile_gate.compile_error
        compile_preservation = compile_gate.compile_preservation
        preserved_compile_error = compile_gate.preserved_compile_error
        candidate_review_path = compile_gate.candidate_review_path
        candidate_score = compile_gate.candidate_score
        candidate_axes = compile_gate.candidate_axes
        no_op_refinement = compile_gate.no_op_refinement
        worklog = compile_gate.worklog
        lane_notes = compile_gate.lane_notes

        if candidate_only:
            state = load_session(cwd)
            apply_candidate_only_refinement_state(
                state,
                temp_state_paper=temp_state_paper,
                temp_latest_review=temp_latest_review,
                validation_path=validation_path,
                temp_review_history_len=temp_review_history_len,
            )
            save_session(cwd, state)
            accepted_results.append(
                candidate_only_result(
                    iteration=iteration.candidate_iter,
                    score_before=previous_score,
                    score_after=candidate_score,
                    axis_scores_before=previous_axes,
                    axis_scores_after=candidate_axes,
                    paper_path=temp_state_paper,
                    candidate_path=candidate_tex_path,
                    candidate_sha256=_file_sha256(candidate_tex_path),
                    worklog_path=worklog_path,
                    compile_error=compile_error,
                    validation_path=validation_path,
                    validation_payload=validation_payload,
                    review_path=candidate_review_path,
                    no_op_refinement=no_op_refinement,
                    contract_regression_preservation=contract_regression_preservation,
                )
            )
            break
        accept = should_accept_refinement_candidate(
            compile_error=compile_error,
            no_op_refinement=no_op_refinement,
            candidate_score=candidate_score,
            previous_score=previous_score,
            candidate_axes=candidate_axes,
            previous_axes=previous_axes,
        )
        retry_review = maybe_retry_refinement_review(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            candidate_iter=iteration.candidate_iter,
            accept=accept,
            no_op_refinement=no_op_refinement,
            compile_error=compile_error,
            previous_score=previous_score,
            candidate_score=candidate_score,
            previous_axes=previous_axes,
            candidate_review_path=candidate_review_path,
        )
        accept = retry_review.accept
        candidate_review_path = retry_review.candidate_review_path
        candidate_score = retry_review.candidate_score
        review_retry_paths = retry_review.review_retry_paths
        review_retry_scores = retry_review.review_retry_scores

        if accept:
            final_path = artifact_path(cwd, "paper.full.tex")
            write_text(final_path, latex)
            lane_path = record_accepted_refinement_lane_manifest(
                cwd,
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                fallback_used=fallback_used,
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(final_path), str(worklog_path), str(validation_path)],
                notes=lane_notes,
            )
            state = load_session(cwd)
            apply_accepted_refinement_state(
                state,
                final_path=final_path,
                candidate_review_path=candidate_review_path,
                candidate_pdf_path=candidate_pdf_path,
                iteration=iteration.candidate_iter,
                previous_score=previous_score,
                candidate_score=candidate_score,
                compile_preservation=compile_preservation,
                review_retry_scores=review_retry_scores,
                lane_manifest_path=lane_path,
            )
            save_session(cwd, state)
            accepted_results.append(
                accepted_refinement_result(
                    iteration=iteration.candidate_iter,
                    compile_preservation=compile_preservation,
                    score_before=previous_score,
                    score_after=candidate_score,
                    paper_path=final_path,
                    worklog_path=worklog_path,
                    compile_error=preserved_compile_error,
                    validation_path=validation_path,
                    validation_payload=validation_payload,
                    lane_manifest_path=lane_path,
                    review_retry_paths=review_retry_paths,
                    review_retry_scores=review_retry_scores,
                )
            )
        else:
            lane_path = record_rejected_refinement_lane_manifest(
                cwd,
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                fallback_used=fallback_used,
                compile_error=compile_error,
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(worklog_path), str(validation_path)],
                notes=lane_notes,
            )
            state = load_session(cwd)
            reason = compile_error or "score_regressed_or_tie_break_failed"
            print(
                f"Refinement iter {iteration.candidate_iter} rejected: score {previous_score} -> {candidate_score}; reason={reason}",
                file=sys.stderr,
            )
            apply_rejected_refinement_state(
                state,
                temp_state_paper=temp_state_paper,
                temp_latest_review=temp_latest_review,
                validation_path=validation_path,
                temp_review_history_len=temp_review_history_len,
                iteration=iteration.candidate_iter,
                previous_score=previous_score,
                candidate_score=candidate_score,
                review_retry_scores=review_retry_scores,
                lane_manifest_path=lane_path,
            )
            save_session(cwd, state)
            accepted_results.append(
                rejected_refinement_result(
                    iteration=iteration.candidate_iter,
                    score_before=previous_score,
                    score_after=candidate_score,
                    paper_path=temp_state_paper,
                    worklog_path=worklog_path,
                    compile_error=compile_error,
                    validation_path=validation_path,
                    validation_payload=validation_payload,
                    lane_manifest_path=lane_path,
                    review_retry_paths=review_retry_paths,
                    review_retry_scores=review_retry_scores,
                )
            )
            break

    return accepted_results
