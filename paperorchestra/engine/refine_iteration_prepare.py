from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session, save_session
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _provider_name
from paperorchestra.engine.latex_postprocess import _drop_unknown_citation_keys
from paperorchestra.engine.prompt_context import _unknown_citation_key_counts
from paperorchestra.engine.refine_context import build_refinement_iteration_context
from paperorchestra.engine.refine_contracts import apply_contract_regression_preservation
from paperorchestra.engine.refine_drafts import normalize_refinement_latex, parse_refinement_response
from paperorchestra.engine.refine_iteration_types import PreparedRefinementDraft
from paperorchestra.engine.reports import collect_paper_contract_issues
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.provider_base import BaseProvider


def prepare_refinement_draft(
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
