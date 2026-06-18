from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_latex, write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _lane_owner,
    _provider_name,
)
from paperorchestra.engine.reports import (
    _blocking_issues,
    _issue_messages,
    _record_validation_report,
)
from paperorchestra.engine.section_scope import _normalize_section_selection
from paperorchestra.engine.section_writing_plan_builder import build_section_writing_plan
from paperorchestra.engine.section_writing_repair import repair_section_draft_if_possible
from paperorchestra.engine.section_writing_support import normalize_section_draft, validate_section_draft
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def write_sections(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    only_sections: list[str] | str | None = None,
    output_path: str | Path | None = None,
    claim_safe: bool = False,
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Need outline.json before write-sections.")

    selected_sections = _normalize_section_selection(only_sections)
    plan = build_section_writing_plan(
        cwd,
        state,
        selected_sections=selected_sections,
        claim_safe=claim_safe,
    )

    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_section_writer_system(),
            user_prompt=plan.user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="section_writing",
    )
    latex = extract_latex(response)
    latex, citation_replacements, dropped_citations = normalize_section_draft(latex, plan.draft_context)

    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)

    latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
    validation_issues = validate_section_draft(latex, plan.validation_context)
    blocking_issues = _blocking_issues(validation_issues)
    repair = repair_section_draft_if_possible(
        cwd=cwd,
        provider=provider,
        runtime_mode=runtime_mode,
        user_prompt=plan.user_prompt,
        latex=latex,
        validation_issues=validation_issues,
        blocking_issues=blocking_issues,
        draft_context=plan.draft_context,
        validation_context=plan.validation_context,
        min_citation_coverage=plan.min_citation_coverage,
        citation_map=plan.citation_map,
        plot_assets_index=plan.plot_assets_index,
        selected_sections=plan.selected_sections,
        strict_claim_safe_prompt=plan.strict_claim_safe_prompt,
        citation_replacements=citation_replacements,
        dropped_citations=dropped_citations,
        lane_notes=lane_notes,
        lane_type=lane_type,
        fallback_used=fallback_used,
    )
    latex = repair.latex
    validation_issues = repair.validation_issues
    blocking_issues = repair.blocking_issues
    lane_notes = repair.lane_notes
    lane_type = repair.lane_type
    fallback_used = repair.fallback_used

    validation_path, _ = _record_validation_report(
        cwd,
        stage="section_writing",
        issues=validation_issues,
        name="validation.sections.json",
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    if blocking_issues:
        raise ContractError(
            "Section writer produced invalid paper contract:\n- " + "\n- ".join(_issue_messages(blocking_issues))
        )
    if validation_issues:
        state.notes.append("Section writer validation warnings: " + " | ".join(_issue_messages(validation_issues)))
    state.notes.append(f"Validation report recorded: {validation_path.name}")

    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "paper.full.tex")
    write_text(path, latex)
    lane_path = record_lane_manifest(
        cwd,
        stage="section_writing",
        role="Section Writing Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[
            state.artifacts.outline_json or "",
            state.artifacts.citation_map_json or "",
            state.artifacts.plot_assets_json or "",
        ],
        output_artifacts=[str(path), str(validation_path)],
        fallback_used=fallback_used,
        notes=lane_notes
        + (
            [f"Section-scoped rewrite requested for: {', '.join(plan.selected_sections)}"]
            if plan.selected_sections
            else []
        ),
    )
    state.artifacts.paper_full_tex = str(path)
    state.current_phase = "iterative_content_refinement"
    state.active_artifact = "paper.full.tex"
    state.notes.append("Full paper draft generated.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path
