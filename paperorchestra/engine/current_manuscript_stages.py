from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, read_text, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, build_path, load_session, save_session
from paperorchestra.engine.latex_plot_reviewable import _reviewable_plot_assets_index, _reviewable_plot_manifest
from paperorchestra.engine.prompt_context import _read_inputs, _source_grounding_text
from paperorchestra.engine.reports import _record_validation_report, collect_paper_contract_issues
from paperorchestra.engine.section_scope import _expected_section_titles_from_outline
from paperorchestra.manuscript.figure_review_builder import build_figure_placement_review
from paperorchestra.manuscript.latex import compile_latex_with_report
from paperorchestra.manuscript.narrative_artifacts import planning_artifact_status
from paperorchestra.visual.page_layout_review import (
    write_page_layout_review as _write_page_layout_review,
    write_visual_repair_candidate as _write_visual_repair_candidate,
    write_visual_repair_brief as _write_visual_repair_brief,
)


def write_figure_placement_review(
    cwd: str | Path | None,
    *,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before figure-placement review.")
    manuscript_path = Path(state.artifacts.paper_full_tex).resolve()
    source_latex = read_text(state.inputs.template_path) if state.inputs.template_path and Path(state.inputs.template_path).exists() else None
    raw_plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else {"figures": []}
    raw_plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else {"assets": []}
    plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
    plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
    payload = build_figure_placement_review(
        manuscript_path.read_text(encoding="utf-8"),
        source_latex=source_latex,
        manuscript_path=str(manuscript_path),
        pdf_path=state.artifacts.compiled_pdf,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
    )
    payload["generated_at"] = utc_now_iso()
    payload["manuscript_sha256"] = hashlib.sha256(manuscript_path.read_bytes()).hexdigest()
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "figure-placement-review.json")
    write_json(path, payload)
    state.artifacts.latest_figure_placement_review_json = str(path)
    save_session(cwd, state)
    return path, payload


def write_page_layout_review(
    cwd: str | Path | None,
    *,
    pdf_path: str | Path | None = None,
    output_path: str | Path | None = None,
    render_dir: str | Path | None = None,
    findings_json: str | Path | None = None,
    review_focus: str | None = None,
    require_ai_artifact_check: bool = False,
    require_publication_figure_check: bool = False,
) -> tuple[Path, dict[str, Any]]:
    return _write_page_layout_review(
        cwd,
        pdf_path=pdf_path,
        output_path=output_path,
        render_dir=render_dir,
        findings_json=findings_json,
        review_focus=review_focus,
        require_ai_artifact_check=require_ai_artifact_check,
        require_publication_figure_check=require_publication_figure_check,
    )


def write_visual_repair_brief(
    cwd: str | Path | None,
    *,
    review_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    return _write_visual_repair_brief(cwd, review_path=review_path, output_path=output_path)


def write_visual_repair_candidate(
    cwd: str | Path | None,
    *,
    brief_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    return _write_visual_repair_candidate(cwd, brief_path=brief_path, output_path=output_path)


def record_current_validation_report(
    cwd: str | Path | None,
    *,
    name: str = "validation.current.json",
) -> tuple[Path, dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before validating the current manuscript.")
    latex = read_text(state.artifacts.paper_full_tex)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    plot_manifest = read_json(state.artifacts.plot_manifest_json) if state.artifacts.plot_manifest_json else None
    plot_assets_index = read_json(state.artifacts.plot_assets_json) if state.artifacts.plot_assets_json else None
    plot_manifest = _reviewable_plot_manifest(plot_manifest, plot_assets_index)
    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else None
    expected_section_titles = _expected_section_titles_from_outline(outline) if isinstance(outline, dict) else None
    validation_inputs = _read_inputs(state)
    experimental_log_text = _source_grounding_text(validation_inputs)
    planning_status = planning_artifact_status(cwd)
    planning_payloads = planning_status.get("payloads") if planning_status.get("status") == "pass" else {}
    issues = collect_paper_contract_issues(
        latex,
        citation_map=citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        experimental_log_text=experimental_log_text,
        expected_section_titles=expected_section_titles,
        narrative_plan=(planning_payloads or {}).get("narrative_plan"),
        claim_map=(planning_payloads or {}).get("claim_map"),
        citation_placement_plan=(planning_payloads or {}).get("citation_placement_plan"),
    )
    path, payload = _record_validation_report(
        cwd,
        stage="current_manuscript",
        issues=issues,
        name=name,
        manuscript_path=state.artifacts.paper_full_tex,
        manuscript_text=latex,
    )
    state = load_session(cwd)
    state.notes.append(f"Current manuscript validation report recorded: {path.name}")
    save_session(cwd, state)
    return path, payload


def compile_current_paper(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before compile.")
    paper_path = Path(state.artifacts.paper_full_tex)
    log_path = build_path(cwd, "latex-build.log")
    report = compile_latex_with_report(paper_path, workdir=build_path(cwd, "compiled"), output_log=log_path)
    compile_report_path = artifact_path(cwd, "compile-report.json")
    write_json(compile_report_path, report.to_dict())
    state.artifacts.latest_compile_report_json = str(compile_report_path)
    if report.pdf_exists and report.pdf_path:
        state.artifacts.compiled_pdf = report.pdf_path
        state.active_artifact = Path(report.pdf_path).name
        if report.clean and state.current_phase == "draft_complete":
            state.current_phase = "complete"
            state.notes.append("Paper compiled successfully with a clean compile.")
        elif report.clean:
            state.notes.append("Paper compiled successfully with a clean compile.")
        else:
            state.notes.append("Paper compiled with warnings/unresolved issues.")
            save_session(cwd, state)
            raise ContractError(f"LaTeX build produced a PDF but has unresolved issues. See log: {report.log_path}")
    else:
        save_session(cwd, state)
        raise ContractError(f"LaTeX build failed. See log: {report.log_path}")
    save_session(cwd, state)
    return Path(report.pdf_path)
