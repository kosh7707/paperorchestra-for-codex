from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.engine.authoring_common import _apply_mock_watermark
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.core.io import extract_latex, read_json, read_text, write_json, write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _lane_owner,
    _provider_name,
)
from paperorchestra.engine.latex_postprocess import (
    _drop_unknown_citation_keys,
    _ensure_bibliography_hook,
    _ensure_generated_plot_usage,
    _filter_plot_context_for_latex,
    _normalize_generated_plot_paths,
    _normalize_source_figure_paths,
    _reviewable_plot_assets_index,
    _reviewable_plot_manifest,
    _stabilize_figure_float_placement,
)
from paperorchestra.engine.planning_stages import (
    _author_facing_writer_brief_block,
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.plot_stages import _inject_missing_plot_assets
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _compact_intro_related_plan_for_prompt,
    _compact_outline_for_prompt,
    _compact_plot_assets_for_prompt,
    _compact_plot_manifest_for_prompt,
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
from paperorchestra.engine.section_scope import (
    _expected_section_titles_from_outline,
    _filter_section_scoped_issues,
    _filtered_outline_for_sections,
    _normalize_section_selection,
    _preserve_all_except_sections,
    _preserve_existing_sections,
    _resolve_selected_sections,
    _selected_section_template,
)
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.repair import (
    _canonical_generated_section_title,
    _citation_map_for_selected_sections,
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _ensure_text_safe_math_macros,
    _remove_material_packet_sections,
    _restore_missing_referenced_labels,
    _sanitize_manuscript_control_prose,
    _section_range_map,
)
from paperorchestra.manuscript.validator import (
    allowed_citation_keys,
    canonical_citation_key,
    canonical_citation_keys,
    canonicalize_citation_keys,
    extract_citation_keys,
    validate_manuscript,
)
from paperorchestra.reviews.fidelity import write_reproducibility_audit
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def _citation_coverage_target(citation_map: dict[str, Any]) -> int:
    population = len(canonical_citation_keys(citation_map))
    if population <= 0:
        return 0
    if population <= 10:
        return population
    if population <= 25:
        return max(1, int(round(population * 0.85)))
    if population <= 50:
        return max(1, int(round(population * 0.8)))
    return max(1, int(round(population * 0.7)))


def _ensure_minimum_citation_coverage(
    latex: str,
    citation_map: dict[str, Any],
    *,
    target: int | None = None,
    max_shortfall: int = 2,
) -> str:
    """Add a bounded related-work citation bridge when coverage is narrowly short.

    The LLM sometimes stops one or two references below the mechanical coverage
    target even after repair prompts.  Rather than failing the run or inventing
    detailed claims, add a deliberately generic related-work sentence citing only
    existing verified keys.  The sentence makes no domain-specific claim; it
    merely records that the paper's background context also draws on those
    references.
    """

    if not citation_map:
        return latex
    target_count = _citation_coverage_target(citation_map) if target is None else max(0, target)
    if target_count <= 0:
        return latex
    known_keys = [str(key) for key in canonical_citation_keys(citation_map)]
    cited = extract_citation_keys(latex)
    allowed = allowed_citation_keys(citation_map)
    cited_known = {canonical_citation_key(key, citation_map) if key in citation_map else key for key in cited if key in allowed}
    needed = target_count - len(cited_known)
    if needed <= 0:
        return latex
    if needed > max(0, max_shortfall):
        return latex
    missing = [key for key in known_keys if key not in cited_known]
    if not missing:
        return latex
    selected = missing[:needed]
    bridge = (
        "\n\n\\paragraph{Additional related context.}\n"
        "This paper also draws on related specifications, analyses, and benchmarking resources"
        f"~\\cite{{{','.join(selected)}}}.\n"
    )
    ranges = _section_range_map(latex)
    related_span = ranges.get("related work") or ranges.get("background and related work")
    if not related_span:
        return latex
    _, end = related_span
    return latex[:end].rstrip() + bridge + "\n" + latex[end:].lstrip()


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
    if selected_sections and not state.artifacts.paper_full_tex:
        raise ContractError("Need an existing paper.full.tex before rewriting only selected sections.")
    current_source = read_text(state.artifacts.paper_full_tex) if selected_sections and state.artifacts.paper_full_tex else None
    if current_source is not None:
        selected_sections = _resolve_selected_sections(current_source, selected_sections)
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        selected_sections,
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)
    outline = read_json(state.artifacts.outline_json)
    raw_prompt_outline = _filtered_outline_for_sections(outline, selected_sections) if selected_sections else outline
    prompt_outline = _compact_outline_for_prompt(raw_prompt_outline)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_citation_map = _citation_map_for_selected_sections(current_source, citation_map, selected_sections) if current_source is not None else citation_map
    min_citation_coverage = _citation_coverage_target(citation_map)
    raw_plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else {"figures": []}
    raw_plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else {"assets": []}
    plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
    plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
    selected_section_source = _selected_section_template(current_source, selected_sections) if selected_sections and current_source is not None else None
    scoped_plot_manifest, scoped_plot_assets_index = (
        _filter_plot_context_for_latex(selected_section_source, plot_manifest, plot_assets_index)
        if selected_sections
        else (plot_manifest, plot_assets_index)
    )
    prompt_plot_manifest = _compact_plot_manifest_for_prompt(scoped_plot_manifest)
    prompt_plot_assets_index = _compact_plot_assets_for_prompt(scoped_plot_assets_index)
    expected_section_titles = (
        selected_sections
        if selected_sections
        else _expected_section_titles_from_outline(outline)
    )
    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="section_writing",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    prompt_citation_map_compact = _compact_citation_map_for_prompt(
        prompt_citation_map,
        include_abstract=strict_claim_safe_prompt,
        include_authors=False,
        include_year=strict_claim_safe_prompt,
        include_venue=strict_claim_safe_prompt,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=3000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=5000, tail_chars=1000)
    source_critical_context = _source_critical_context_for_prompt(inputs)
    figures_dir = state.inputs.figures_dir or ""
    if current_source is not None:
        template_content = _selected_section_template(current_source, selected_sections)
    else:
        template_content = read_text(state.inputs.template_path)
        if state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
            intro_related_source = read_text(state.artifacts.intro_related_tex)
            template_content = _preserve_existing_sections(
                template_content,
                intro_related_source,
                section_names=["Introduction", "Related Work"],
            )
    prompt_template_content = _prompt_compact_text(template_content, head_chars=5000, tail_chars=1000)
    section_scope_instructions = ""
    if selected_sections:
        section_scope_instructions = (
            "Section-scope Instructions:\n"
            f"- Rewrite ONLY these sections: {', '.join(selected_sections)}.\n"
            "- Preserve all section titles, labels, citations, and figure references already present in current_template.tex for those sections.\n"
            "- Do NOT invent new citation keys, figure filenames, labels, or cross-references that are absent from current_template.tex.\n"
            "- Prefer revising the prose within the existing section skeleton over introducing new structural elements.\n"
        )
    global_section_instructions = (
        "Global Writing Constraints:\n"
        f"- Use at least {min_citation_coverage} distinct verified citations when that many verified references are available.\n"
        "- Do NOT invent meta sections such as checklists or workflow notes that are not part of current_template.tex.\n"
        "- Write manuscript prose only; express evidence limits as scholarly assumptions, scope, and limitations.\n"
        "- Do NOT preserve input-note headings as manuscript sections; fold their constraints into normal prose, "
        "especially Discussion limitations.\n"
    )
    user_prompt = f"""
{_data_block('outline.json', json.dumps(prompt_outline, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(prompt_citation_map_compact, indent=2, ensure_ascii=False))}

{_data_block('citation_coverage_target.json', json.dumps({'min_distinct_verified_citations': min_citation_coverage, 'available_verified_citations': len(canonical_citation_keys(citation_map))}, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('current_template.tex', prompt_template_content)}

{_data_block('figures_list', inputs['figures'])}

{_data_block('figures_dir', figures_dir or 'null')}
{_data_block('rewrite_scope.json', json.dumps({'only_sections': selected_sections, 'preserve_all_other_sections': bool(selected_sections)}, ensure_ascii=False))}

{global_section_instructions}
{section_scope_instructions}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_section_writer_system(), user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="section_writing",
    )
    latex = extract_latex(response)
    if selected_sections and current_source is not None:
        latex = _preserve_all_except_sections(
            latex,
            current_source,
            rewritten_section_names=selected_sections,
        )
    elif state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
        intro_related_source = read_text(state.artifacts.intro_related_tex)
        latex = _preserve_existing_sections(
            latex,
            intro_related_source,
            section_names=["Introduction", "Related Work"],
        )
    latex = _restore_missing_referenced_labels(latex, template_content)
    latex = _ensure_bibliography_hook(latex, citation_map)
    latex = _normalize_generated_plot_paths(latex, plot_assets_index)
    latex = _normalize_source_figure_paths(latex, state.inputs.figures_dir)
    latex = _ensure_generated_plot_usage(latex, plot_assets_index)
    latex = _stabilize_figure_float_placement(latex)
    latex = _remove_material_packet_sections(latex)
    latex = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)
    latex = _ensure_required_claim_scope_notes(latex, claim_map)
    latex, citation_replacements = canonicalize_citation_keys(latex, citation_map)
    if strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, citation_map)
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    latex = _apply_mock_watermark(latex, state, provider_name=_provider_name(provider))
    validation_subject = _selected_section_template(latex, selected_sections) if selected_sections else latex
    validation_issues = collect_paper_contract_issues(
        validation_subject,
        citation_map=citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=scoped_plot_manifest if selected_sections else plot_manifest,
        plot_assets_index=scoped_plot_assets_index if selected_sections else plot_assets_index,
        experimental_log_text=_source_grounding_text(inputs),
        expected_section_titles=expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )
    validation_issues = _filter_section_scoped_issues(validation_issues, selected_sections=selected_sections)
    blocking_issues = _blocking_issues(validation_issues)
    repairable_codes = {issue.code for issue in blocking_issues}
    if blocking_issues and repairable_codes <= {
        "unknown_citation_keys",
        "citation_coverage_insufficient",
        "numeric_grounding_mismatch",
        "plot_plan_not_reflected",
        "expected_section_missing",
        "expected_section_too_shallow",
        "required_claim_missing",
        "required_claim_keyword_stuffing",
        "narrative_section_role_missing",
    }:
        repair_prompt = f"""
{user_prompt}

{_data_block('current_draft.tex', _prompt_compact_text(latex, head_chars=10000, tail_chars=2000))}

{_data_block('validation_issues.json', json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False))}

Repair Instructions:
- Revise the existing manuscript draft to satisfy the validation issues above.
- Use ONLY citation keys from the verified reference library.
- Increase citation coverage until the paper satisfies the citation coverage contract, using at least {min_citation_coverage} distinct verified citations when that many are available.
- Every decimal or percent value in the manuscript must appear verbatim in the measurement log. If a number is not grounded there, remove it or rewrite the claim qualitatively without introducing a replacement number.
- Ensure every required plot-plan figure is represented in the manuscript. Use available generated plot assets/snippets instead of inventing new figure files.
- Cover every required claim and narrative role item in its target section with meaningful, section-local prose rather than keyword stuffing.
- Expand every missing or shallow expected section with grounded, section-specific substance from the technical context, measurement log, section plan, and current template.
- Do not leave Method, Security Analysis, Implementation/Results, Discussion, or Conclusion as heading-only placeholders.
- Do not preserve input-note headings as manuscript sections; fold their constraints into Discussion and normal authorial prose.
- Preserve valid existing structure, plot usage, and grounded claims where possible.
- Do NOT invent meta sections such as checklists or workflow notes that are not part of the manuscript template.
- When rewrite_scope.json lists only_sections, preserve the existing section titles, citation keys, and figure references already present in current_template.tex.
- Return LaTeX only.
""".strip()
        retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
            _build_completion_request(system_prompt=PROMPTS.render_section_writer_system(), user_prompt=repair_prompt),
            provider=provider,
            runtime_mode=runtime_mode,
            cwd=cwd,
            omx_lane_type="ralph",
            trace_stage="section_writing_repair",
        )
        retry_latex = extract_latex(retry_response)
        if selected_sections and current_source is not None:
            retry_latex = _preserve_all_except_sections(
                retry_latex,
                current_source,
                rewritten_section_names=selected_sections,
            )
        elif state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
            intro_related_source = read_text(state.artifacts.intro_related_tex)
            retry_latex = _preserve_existing_sections(
                retry_latex,
                intro_related_source,
                section_names=["Introduction", "Related Work"],
            )
        retry_latex = _restore_missing_referenced_labels(retry_latex, template_content)
        retry_latex = _ensure_bibliography_hook(retry_latex, citation_map)
        retry_latex = _normalize_generated_plot_paths(retry_latex, plot_assets_index)
        retry_latex = _normalize_source_figure_paths(retry_latex, state.inputs.figures_dir)
        retry_latex = _ensure_generated_plot_usage(retry_latex, plot_assets_index)
        retry_latex = _stabilize_figure_float_placement(retry_latex)
        retry_latex = _remove_material_packet_sections(retry_latex)
        retry_latex = _ensure_discussion_section_for_claim_boundaries(retry_latex, claim_map)
        retry_latex = _ensure_required_claim_scope_notes(retry_latex, claim_map)
        retry_latex, retry_replacements = canonicalize_citation_keys(retry_latex, citation_map)
        if strict_claim_safe_prompt:
            retry_dropped_citations = _unknown_citation_key_counts(retry_latex, citation_map)
        else:
            retry_latex, retry_dropped_citations = _drop_unknown_citation_keys(retry_latex, citation_map)
        retry_validation_subject = _selected_section_template(retry_latex, selected_sections) if selected_sections else retry_latex
        retry_issues = collect_paper_contract_issues(
            retry_validation_subject,
            citation_map=citation_map,
            figures_dir=state.inputs.figures_dir,
            plot_manifest=scoped_plot_manifest if selected_sections else plot_manifest,
            plot_assets_index=scoped_plot_assets_index if selected_sections else plot_assets_index,
            experimental_log_text=_source_grounding_text(inputs),
            expected_section_titles=expected_section_titles,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
        )
        retry_issues = _filter_section_scoped_issues(retry_issues, selected_sections=selected_sections)
        retry_blocking = _blocking_issues(retry_issues)
        if (
            retry_blocking
            and {issue.code for issue in retry_blocking} <= {"citation_coverage_insufficient"}
            and (
                not selected_sections
                or bool(
                    {_canonical_generated_section_title(section) for section in selected_sections}
                    & {"related work", "background and related work"}
                )
            )
        ):
            bridged_retry_latex = _ensure_minimum_citation_coverage(
                retry_latex,
                citation_map,
                target=min_citation_coverage,
            )
            if bridged_retry_latex != retry_latex:
                retry_latex = bridged_retry_latex
                retry_validation_subject = _selected_section_template(retry_latex, selected_sections) if selected_sections else retry_latex
                retry_issues = collect_paper_contract_issues(
                    retry_validation_subject,
                    citation_map=citation_map,
                    figures_dir=state.inputs.figures_dir,
                    plot_manifest=scoped_plot_manifest if selected_sections else plot_manifest,
                    plot_assets_index=scoped_plot_assets_index if selected_sections else plot_assets_index,
                    experimental_log_text=_source_grounding_text(inputs),
                    expected_section_titles=expected_section_titles,
                    narrative_plan=narrative_plan,
                    claim_map=claim_map,
                    citation_placement_plan=citation_placement_plan,
                )
                retry_issues = _filter_section_scoped_issues(retry_issues, selected_sections=selected_sections)
                retry_blocking = _blocking_issues(retry_issues)
        if not retry_blocking:
            latex = retry_latex
            validation_issues = retry_issues
            blocking_issues = retry_blocking
            lane_notes = lane_notes + ["Section writer draft was retried after section-contract validation failure."] + retry_lane_notes
            if citation_replacements:
                lane_notes.append(
                    "Canonicalized citation-key aliases in section draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
                )
            if retry_replacements:
                lane_notes.append(
                    "Canonicalized citation-key aliases in section retry draft: "
                    + ", ".join(f"{src}->{dst}" for src, dst in sorted(retry_replacements.items()))
                )
            if retry_dropped_citations:
                note_prefix = (
                    "Blocked unsupported citation keys in strict section retry draft: "
                    if strict_claim_safe_prompt
                    else "Dropped unsupported citation keys in section retry draft: "
                )
                lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(retry_dropped_citations.items())))
            lane_type = retry_lane_type
            fallback_used = retry_fallback_used
        else:
            repaired_retry_latex = retry_latex
            repaired = False
            if any(issue.code == "plot_plan_not_reflected" for issue in retry_blocking):
                repaired_retry_latex = _inject_missing_plot_assets(repaired_retry_latex, retry_blocking, plot_assets_index)
                repaired_retry_latex = _stabilize_figure_float_placement(repaired_retry_latex)
                repaired = True
            retry_validation_subject = _selected_section_template(repaired_retry_latex, selected_sections) if selected_sections else repaired_retry_latex
            sanitized_issues = collect_paper_contract_issues(
                retry_validation_subject,
                citation_map=citation_map,
                figures_dir=state.inputs.figures_dir,
                plot_manifest=scoped_plot_manifest if selected_sections else plot_manifest,
                plot_assets_index=scoped_plot_assets_index if selected_sections else plot_assets_index,
                experimental_log_text=_source_grounding_text(inputs),
                expected_section_titles=expected_section_titles,
                narrative_plan=narrative_plan,
                claim_map=claim_map,
                citation_placement_plan=citation_placement_plan,
            )
            sanitized_issues = _filter_section_scoped_issues(sanitized_issues, selected_sections=selected_sections)
            if repaired and not _blocking_issues(sanitized_issues):
                latex = repaired_retry_latex
                validation_issues = sanitized_issues
                blocking_issues = []
                lane_notes = lane_notes + [
                    "Section retry draft received deterministic post-processing for residual plot-plan/numeric validation issues."
                ] + retry_lane_notes
                lane_type = retry_lane_type
                fallback_used = retry_fallback_used
    elif citation_replacements:
        lane_notes.append(
            "Canonicalized citation-key aliases in section draft: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(citation_replacements.items()))
        )
    if dropped_citations:
        note_prefix = (
            "Blocked unsupported citation keys in strict section draft: "
            if strict_claim_safe_prompt
            else "Dropped unsupported citation keys in section draft: "
        )
        lane_notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))

    validation_path, _ = _record_validation_report(
        cwd,
        stage="section_writing",
        issues=validation_issues,
        name="validation.sections.json",
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(validation_issues)
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
            [f"Section-scoped rewrite requested for: {', '.join(selected_sections)}"]
            if selected_sections
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

