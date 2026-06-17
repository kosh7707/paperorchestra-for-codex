from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_latex, read_json, write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.citation_coverage import _citation_coverage_target, _ensure_minimum_citation_coverage
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _lane_owner,
    _provider_name,
)
from paperorchestra.engine.latex_postprocess import _drop_unknown_citation_keys
from paperorchestra.engine.planning_stages import (
    _author_facing_writer_brief_block,
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _compact_intro_related_plan_for_prompt,
    _data_block,
    _prompt_compact_text,
    _raise_if_strict_source_citations_unmapped,
    _read_inputs,
    _source_critical_context_for_prompt,
    _source_grounding_text,
    _strict_content_gates_enabled,
    _unknown_citation_key_counts,
)
from paperorchestra.engine.reports import (
    _blocking_issues,
    _issue_messages,
    _record_validation_report,
    collect_paper_contract_issues,
)
from paperorchestra.engine.section_scope import _preserve_all_except_sections
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.repair import _remove_material_packet_sections, _sanitize_manuscript_control_prose
from paperorchestra.manuscript.validator import canonical_citation_keys, canonicalize_citation_keys
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def write_intro_related(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    allow_recoverable_contract_issues: bool = False,
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json or not state.artifacts.citation_map_json:
        raise ContractError("Need outline.json and citation_map.json before writing intro/related work.")
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        ["Introduction", "Related Work"],
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)
    outline = read_json(state.artifacts.outline_json)
    citation_map = read_json(state.artifacts.citation_map_json)
    min_citation_coverage = _citation_coverage_target(citation_map)
    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="intro_related",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    prompt_intro_related_plan = _compact_intro_related_plan_for_prompt(outline["intro_related_work_plan"])
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
    prompt_template = _prompt_compact_text(inputs["template"], head_chars=5000, tail_chars=500)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=4000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=7000, tail_chars=1500)
    source_critical_context = _source_critical_context_for_prompt(inputs)
    user_prompt = f"""
{_data_block('template.tex', prompt_template)}

{_data_block('intro_related_authoring_plan', json.dumps(prompt_intro_related_plan, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('project_idea', prompt_idea)}

{_data_block('project_experimental_log', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_checklist', json.dumps(sorted(canonical_citation_keys(citation_map)), indent=2, ensure_ascii=False))}

{_data_block('collected_papers', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('paper_count', str(len(canonical_citation_keys(citation_map))))}

{_data_block('min_cite_paper_count', str(min_citation_coverage))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_intro_related_system(
                paper_count=len(canonical_citation_keys(citation_map)),
                min_cite_paper_count=min_citation_coverage,
                cutoff_date=state.inputs.cutoff_date,
            ),
            user_prompt=user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="intro_related",
    )
    latex = extract_latex(response)
    latex = _preserve_all_except_sections(
        latex,
        inputs["template"],
        rewritten_section_names=["Introduction", "Related Work"],
    )
    latex = _remove_material_packet_sections(latex)
    latex = _sanitize_manuscript_control_prose(latex)
    latex, citation_replacements = canonicalize_citation_keys(latex, citation_map)
    if strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
    validation_issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=None,
        plot_manifest=None,
        experimental_log_text=_source_grounding_text(inputs),
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    blocking_issues = _blocking_issues(validation_issues)
    repairable_codes = {issue.code for issue in blocking_issues}
    if blocking_issues and repairable_codes <= {"unknown_citation_keys", "citation_coverage_insufficient", "numeric_grounding_mismatch"}:
        repair_attempt = 0
        while blocking_issues and repair_attempt < 2:
            repair_attempt += 1
            repair_prompt = f"""
{user_prompt}

{_data_block('current_intro_related_draft.tex', _prompt_compact_text(latex, head_chars=12000, tail_chars=2000))}

{_data_block('validation_issues.json', json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False))}

Repair Instructions:
- Revise the existing Introduction/Related Work draft to satisfy the exact validation issues above.
- Use ONLY citation keys from citation_checklist.
- Increase citation coverage until it satisfies min_cite_paper_count.
- Every decimal or percent value in the LaTeX must appear verbatim in project_experimental_log. If a number is not grounded there, remove it or rewrite the sentence qualitatively without introducing a replacement number.
- Preserve valid existing prose where possible and return LaTeX only.
""".strip()
            retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
                _build_completion_request(
                    system_prompt=PROMPTS.render_intro_related_system(
                        paper_count=len(canonical_citation_keys(citation_map)),
                        min_cite_paper_count=min_citation_coverage,
                        cutoff_date=state.inputs.cutoff_date,
                    ),
                    user_prompt=repair_prompt,
                ),
                provider=provider,
                runtime_mode=runtime_mode,
                cwd=cwd,
                omx_lane_type="ralph",
                trace_stage="intro_related_repair" if repair_attempt == 1 else f"intro_related_repair_{repair_attempt}",
            )
            retry_latex = extract_latex(retry_response)
            retry_latex = _preserve_all_except_sections(
                retry_latex,
                inputs["template"],
                rewritten_section_names=["Introduction", "Related Work"],
            )
            retry_latex = _remove_material_packet_sections(retry_latex)
            retry_latex = _sanitize_manuscript_control_prose(retry_latex)
            retry_latex, retry_replacements = canonicalize_citation_keys(retry_latex, citation_map)
            if strict_claim_safe_prompt:
                retry_dropped_citations = _unknown_citation_key_counts(retry_latex, citation_map)
            else:
                retry_latex, retry_dropped_citations = _drop_unknown_citation_keys(retry_latex, citation_map)
            retry_issues = collect_paper_contract_issues(
                retry_latex,
                citation_map=citation_map,
                figures_dir=None,
                plot_manifest=None,
                experimental_log_text=_source_grounding_text(inputs),
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            retry_blocking = _blocking_issues(retry_issues)
            latex = retry_latex
            validation_issues = retry_issues
            blocking_issues = retry_blocking
            repairable_codes = {issue.code for issue in blocking_issues}
            lane_notes = lane_notes + [
                f"Introduction/Related Work draft repair attempt {repair_attempt} ran after citation-contract validation failure."
            ] + retry_lane_notes
            if citation_replacements and repair_attempt == 1:
                lane_notes.append(
                    "Canonicalized citation-key aliases in Introduction/Related Work draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
                )
            if retry_replacements:
                lane_notes.append(
                    f"Canonicalized citation-key aliases in Introduction/Related Work repair attempt {repair_attempt}: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(retry_replacements.items()))
                )
            if retry_dropped_citations:
                note_prefix = (
                    f"Blocked unsupported citation keys in strict Introduction/Related Work repair attempt {repair_attempt}: "
                    if strict_claim_safe_prompt
                    else f"Dropped unsupported citation keys in Introduction/Related Work repair attempt {repair_attempt}: "
                )
                lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(retry_dropped_citations.items())))
            lane_type = retry_lane_type
            fallback_used = retry_fallback_used
            if not blocking_issues:
                break
            if repairable_codes - {"unknown_citation_keys", "citation_coverage_insufficient", "numeric_grounding_mismatch"}:
                break
    elif citation_replacements:
        lane_notes.append(
            "Canonicalized citation-key aliases in Introduction/Related Work draft: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
        )
    if dropped_citations:
        note_prefix = (
            "Blocked unsupported citation keys in strict Introduction/Related Work draft: "
            if strict_claim_safe_prompt
            else "Dropped unsupported citation keys in Introduction/Related Work draft: "
        )
        lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

    if {issue.code for issue in _blocking_issues(validation_issues)} <= {"citation_coverage_insufficient"}:
        bridged_latex = _ensure_minimum_citation_coverage(latex, citation_map, target=min_citation_coverage)
        if bridged_latex != latex:
            bridged_issues = collect_paper_contract_issues(
                bridged_latex,
                citation_map=citation_map,
                figures_dir=None,
                plot_manifest=None,
                experimental_log_text=_source_grounding_text(inputs),
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            latex = bridged_latex
            validation_issues = bridged_issues
            lane_notes.append(
                "Added a bounded related-work citation bridge after repair attempts left only a small citation-coverage shortfall."
            )

    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    validation_path, _ = _record_validation_report(
        cwd,
        stage="intro_related",
        issues=validation_issues,
        name="validation.intro_related.json",
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(validation_issues)
    tolerated_recoverable_issues = (
        allow_recoverable_contract_issues
        and bool(blocking_issues)
        and {issue.code for issue in blocking_issues} <= {"citation_coverage_insufficient"}
    )
    if blocking_issues:
        state.notes.append(
            "Introduction/Related Work recoverable validation blockers: "
            + " | ".join(_issue_messages(blocking_issues))
        )
        if not tolerated_recoverable_issues:
            save_session(cwd, state)
            raise ContractError(
                "Introduction/Related Work output failed contract validation:\n- "
                + "\n- ".join(_issue_messages(blocking_issues))
            )
        lane_notes.append(
            "Persisted a recoverable Introduction/Related Work candidate despite citation-coverage shortfall "
            "so the supervised QA/operator loop can repair it instead of aborting the live smoke early."
        )
    elif validation_issues:
        state.notes.append(
            "Introduction/Related Work validation warnings: " + " | ".join(_issue_messages(validation_issues))
        )
    state.notes.append(f"Validation report recorded: {validation_path.name}")
    path = artifact_path(cwd, "introduction_related_work.tex")
    write_text(path, latex)
    lane_path = record_lane_manifest(
        cwd,
        stage="intro_related",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or "", state.artifacts.citation_map_json or ""],
        output_artifacts=[str(path), str(validation_path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.intro_related_tex = str(path)
    state.current_phase = "section_writing"
    state.active_artifact = "introduction_related_work.tex"
    state.notes.append("Introduction and Related Work drafted.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path
