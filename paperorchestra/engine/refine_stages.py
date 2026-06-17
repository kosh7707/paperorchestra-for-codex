from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import ExtractionError, extract_json, extract_latex, read_json, read_text, write_json, write_text
from paperorchestra.core.session import artifact_path, build_path, load_session, review_path, save_session
from paperorchestra.engine.authoring_common import _append_unique_note, _apply_mock_watermark
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _file_sha256,
    _lane_owner,
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
from paperorchestra.engine.refine_drafts import normalize_refinement_latex, parse_refinement_response
from paperorchestra.engine.refine_results import (
    accepted_refinement_result,
    candidate_only_result,
    contract_validation_failed_result,
    rejected_refinement_result,
)
from paperorchestra.engine.refine_review import _accept_review_delta, _redact_review_scores_for_writer
from paperorchestra.engine.review_stages import _extract_axis_scores, review_current_paper
from paperorchestra.engine.section_scope import _expected_section_titles_from_outline
from paperorchestra.manuscript.latex import compile_latex
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.repair import (
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _remove_material_packet_sections,
)
from paperorchestra.manuscript.validator import canonicalize_citation_keys
from paperorchestra.runtime.parity import record_lane_manifest
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
        current_paper = read_text(state.artifacts.paper_full_tex)
        review_payload = read_json(state.artifacts.latest_review_json)
        citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
        raw_plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else {"figures": []}
        raw_plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else {"assets": []}
        plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
        plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
        outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
        expected_section_titles = _expected_section_titles_from_outline(outline)
        inputs = _read_inputs(state)
        strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
        _raise_if_strict_source_citations_unmapped(
            inputs,
            citation_map,
            stage="refinement",
            strict_claim_safe=strict_claim_safe_prompt,
        )
        experimental_log_text = read_text(state.inputs.experimental_log_path)
        candidate_iter = state.refinement_iteration + 1
        previous_worklog_path = review_path(cwd, f"refinement_worklog.iter-{state.refinement_iteration:02d}.json")
        previous_worklog = read_text(previous_worklog_path) if previous_worklog_path.exists() else "{}"
        prompt_paper_text = _prompt_compact_text(current_paper, head_chars=22000, tail_chars=4000)
        prompt_citation_map = _compact_citation_map_for_prompt(
            citation_map,
            include_abstract=strict_claim_safe_prompt,
            include_authors=False,
            include_year=strict_claim_safe_prompt,
            include_venue=strict_claim_safe_prompt,
            include_provenance=False,
            include_origin=False,
            include_matched_query=False,
        )
        prompt_experimental_log = _prompt_compact_text(experimental_log_text, head_chars=8000, tail_chars=1500)
        source_critical_context = _source_critical_context_for_prompt(inputs)
        prompt_plot_manifest = {"figures": plot_manifest.get("figures", [])[:8]} if isinstance(plot_manifest, dict) else plot_manifest
        prompt_plot_assets_index = (
            {"assets": plot_assets_index.get("assets", [])[:8]}
            if isinstance(plot_assets_index, dict)
            else plot_assets_index
        )
        writer_review_payload = _redact_review_scores_for_writer(review_payload)
        user_prompt = f"""
{_data_block('paper.tex', prompt_paper_text)}

{_data_block('reviewer_feedback', json.dumps(writer_review_payload, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('worklog.json', previous_worklog)}
""".strip()
        response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
            _build_completion_request(system_prompt=PROMPTS.render_refine_system(), user_prompt=user_prompt),
            provider=provider,
            runtime_mode=runtime_mode,
            cwd=cwd,
            omx_lane_type="refiner",
            trace_stage="refinement",
        )
        worklog, latex, lane_notes = parse_refinement_response(response, lane_notes=lane_notes)
        latex, citation_replacements = normalize_refinement_latex(
            latex,
            citation_map=citation_map,
            plot_assets_index=plot_assets_index,
            figures_dir=state.inputs.figures_dir,
            claim_map=claim_map,
        )
        if strict_claim_safe_prompt:
            dropped_citations = _unknown_citation_key_counts(latex, citation_map)
        else:
            latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
        state.latest_provider_name = _provider_name(provider)
        state.latest_runtime_mode = runtime_mode
        save_session(cwd, state)
        latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
        validation_issues = collect_paper_contract_issues(
            latex,
            citation_map=citation_map,
            figures_dir=state.inputs.figures_dir,
            plot_manifest=plot_manifest,
            plot_assets_index=plot_assets_index,
            experimental_log_text=experimental_log_text,
            expected_section_titles=expected_section_titles,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
        )
        blocking_issues = _blocking_issues(validation_issues)
        contract_regression_preservation: dict[str, Any] | None = None
        if blocking_issues:
            preserved_issues = collect_paper_contract_issues(
                current_paper,
                citation_map=citation_map,
                figures_dir=state.inputs.figures_dir,
                plot_manifest=plot_manifest,
                plot_assets_index=plot_assets_index,
                experimental_log_text=experimental_log_text,
                expected_section_titles=expected_section_titles,
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            if not _blocking_issues(preserved_issues):
                rejected_candidate_path = artifact_path(cwd, f"paper.refined.iter-{candidate_iter:02d}.rejected-contract.tex")
                write_text(rejected_candidate_path, latex)
                rejected_validation_path, _rejected_validation_payload = _record_validation_report(
                    cwd,
                    stage="refinement_rejected_contract_regression",
                    issues=validation_issues,
                    name=f"validation.refine.iter-{candidate_iter:02d}.rejected-contract.json",
                    manuscript_text=latex,
                )
                contract_regression_preservation = {
                    "preserved_prior_after_contract_regression": True,
                    "rejected_candidate_path": str(rejected_candidate_path),
                    "rejected_candidate_sha256": _file_sha256(rejected_candidate_path),
                    "contract_regression_issue_count": len(_blocking_issues(validation_issues)),
                    "contract_regression_validation_report_path": str(rejected_validation_path),
                }
                latex = current_paper
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
                if strict_claim_safe_prompt
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
                    score_before=state.review_history[-1].overall_score if state.review_history else float(review_payload.get("overall_score", 0.0)),
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

        candidate_tex_path = artifact_path(cwd, f"paper.refined.iter-{candidate_iter:02d}.tex")
        worklog_path = review_path(cwd, f"refinement_worklog.iter-{candidate_iter:02d}.json")
        write_text(candidate_tex_path, latex)
        write_json(worklog_path, worklog)

        temp_state_paper = state.artifacts.paper_full_tex
        temp_latest_review = state.artifacts.latest_review_json
        temp_review_history_len = len(state.review_history)
        previous_snapshot = state.review_history[-1] if state.review_history else None
        previous_score = previous_snapshot.overall_score if previous_snapshot else float(review_payload.get("overall_score", 0.0))
        previous_axes = previous_snapshot.axes if previous_snapshot else _extract_axis_scores(review_payload)
        no_op_refinement = latex == current_paper
        if no_op_refinement:
            candidate_review_path = Path(temp_latest_review or state.artifacts.latest_review_json or "")
            candidate_review = review_payload
            candidate_score = previous_score
            candidate_axes = previous_axes
        else:
            state.artifacts.paper_full_tex = str(candidate_tex_path)
            save_session(cwd, state)
            candidate_review_path = review_current_paper(
                cwd,
                provider,
                review_name=f"review.iter-{candidate_iter:02d}.json",
                runtime_mode=runtime_mode,
            )
            candidate_review = read_json(candidate_review_path)
            candidate_score = float(candidate_review.get("overall_score", 0.0))
            candidate_axes = _extract_axis_scores(candidate_review)
        candidate_pdf_path = None
        compile_error = None
        compile_preservation = False
        preserved_compile_error = None
        if require_compile_for_accept:
            try:
                candidate_pdf_path = compile_latex(
                    candidate_tex_path,
                    workdir=build_path(cwd, f"compiled-iter-{candidate_iter:02d}"),
                    output_log=build_path(cwd, f"latex-build.iter-{candidate_iter:02d}.log"),
                )
            except Exception as exc:  # pragma: no cover - compile availability is environment-dependent
                compile_error = str(exc)
                preserved_compile_error = compile_error
                previous_compile_report = (
                    read_json(state.artifacts.latest_compile_report_json)
                    if state.artifacts.latest_compile_report_json and Path(state.artifacts.latest_compile_report_json).exists()
                    else None
                )
                if (
                    isinstance(previous_compile_report, dict)
                    and previous_compile_report.get("clean")
                    and previous_compile_report.get("pdf_exists")
                ):
                    latex = current_paper
                    candidate_pdf_path = state.artifacts.compiled_pdf
                    compile_error = None
                    compile_preservation = True
                    no_op_refinement = True
                    candidate_review_path = Path(temp_latest_review or state.artifacts.latest_review_json or "")
                    candidate_review = review_payload
                    candidate_score = previous_score
                    candidate_axes = previous_axes
                    worklog.setdefault("actions_taken", []).append(
                        "Preserved the pre-refinement compiled manuscript because the generated revision failed compile acceptance."
                    )
                    lane_notes = lane_notes + ["Refinement revision failed compile acceptance; preserved prior compiled manuscript."]
                    print(
                        f"Refinement iter {candidate_iter} preserved prior compiled manuscript after compile failure.",
                        file=sys.stderr,
                    )

        review_retry_paths: list[str] = []
        review_retry_scores: list[float] = []
        if candidate_only:
            state = load_session(cwd)
            state.artifacts.paper_full_tex = temp_state_paper
            state.artifacts.latest_review_json = temp_latest_review
            state.artifacts.latest_validation_json = str(validation_path)
            state.review_history = state.review_history[:temp_review_history_len]
            save_session(cwd, state)
            accepted_results.append(
                candidate_only_result(
                    iteration=candidate_iter,
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
        accept = compile_error is None and (no_op_refinement or _accept_review_delta(candidate_score, previous_score, candidate_axes, previous_axes))
        if (
            not accept
            and not no_op_refinement
            and compile_error is None
            and previous_score - candidate_score <= 1.0
        ):
            retry_review_path = review_current_paper(
                cwd,
                provider,
                review_name=f"review.iter-{candidate_iter:02d}.retry-01.json",
                runtime_mode=runtime_mode,
            )
            retry_review = read_json(retry_review_path)
            retry_score = float(retry_review.get("overall_score", 0.0))
            retry_axes = _extract_axis_scores(retry_review)
            review_retry_paths.append(str(retry_review_path))
            review_retry_scores.append(retry_score)
            if _accept_review_delta(retry_score, previous_score, retry_axes, previous_axes):
                candidate_review_path = retry_review_path
                candidate_review = retry_review
                candidate_score = retry_score
                candidate_axes = retry_axes
                accept = True

        if accept:
            final_path = artifact_path(cwd, "paper.full.tex")
            write_text(final_path, latex)
            lane_path = record_lane_manifest(
                cwd,
                stage="refinement",
                role="Content Refinement Agent",
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                owner=_lane_owner(lane_type, fallback_used),
                status="fallback_completed" if fallback_used else "completed",
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(final_path), str(worklog_path), str(validation_path)],
                fallback_used=fallback_used,
                notes=lane_notes,
            )
            state = load_session(cwd)
            state.artifacts.paper_full_tex = str(final_path)
            state.artifacts.latest_review_json = str(candidate_review_path)
            if candidate_pdf_path is not None:
                state.artifacts.compiled_pdf = str(candidate_pdf_path)
                state.current_phase = "complete"
                state.active_artifact = Path(candidate_pdf_path).name
            else:
                state.active_artifact = final_path.name
            state.refinement_iteration = candidate_iter
            state.notes.append(
                f"Accepted refinement iteration {candidate_iter} (score {previous_score} -> {candidate_score})."
            )
            if compile_preservation:
                _append_unique_note(
                    state,
                    f"Compile-failed refinement iteration {candidate_iter} preserved the prior compiled manuscript.",
                )
            if review_retry_scores:
                state.notes.append(
                    "Refinement acceptance used reviewer retry confirmation: "
                    + ", ".join(str(score) for score in review_retry_scores)
                )
            state.notes.append(f"Lane manifest recorded: {lane_path.name}")
            save_session(cwd, state)
            accepted_results.append(
                accepted_refinement_result(
                    iteration=candidate_iter,
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
            lane_path = record_lane_manifest(
                cwd,
                stage="refinement",
                role="Content Refinement Agent",
                runtime_mode=runtime_mode,
                lane_type=lane_type,
                owner=_lane_owner(lane_type, fallback_used),
                status="blocked" if compile_error else "failed",
                input_artifacts=[temp_state_paper, temp_latest_review or ""],
                output_artifacts=[str(worklog_path), str(validation_path)],
                fallback_used=fallback_used,
                notes=lane_notes,
            )
            state = load_session(cwd)
            state.artifacts.paper_full_tex = temp_state_paper
            state.artifacts.latest_review_json = temp_latest_review
            state.artifacts.latest_validation_json = str(validation_path)
            state.review_history = state.review_history[:temp_review_history_len]
            _append_unique_note(
                state,
                f"Rejected refinement iteration {candidate_iter} (score {previous_score} -> {candidate_score}).",
            )
            reason = compile_error or "score_regressed_or_tie_break_failed"
            print(
                f"Refinement iter {candidate_iter} rejected: score {previous_score} -> {candidate_score}; reason={reason}",
                file=sys.stderr,
            )
            if review_retry_scores:
                state.notes.append(
                    "Refinement rejection persisted after reviewer retry: "
                    + ", ".join(str(score) for score in review_retry_scores)
                )
            state.notes.append(f"Lane manifest recorded: {lane_path.name}")
            save_session(cwd, state)
            accepted_results.append(
                rejected_refinement_result(
                    iteration=candidate_iter,
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
