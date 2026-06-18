from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, read_json, read_text, write_json
from paperorchestra.core.models import ScoreSnapshot, utc_now_iso
from paperorchestra.core.session import artifact_path, build_path, load_session, review_path, save_session
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _lane_owner,
    _provider_name,
    _review_provenance_payload,
)
from paperorchestra.engine.latex_postprocess import _reviewable_plot_assets_index, _reviewable_plot_manifest
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _data_block,
    _prompt_compact_text,
    _read_inputs,
    _source_grounding_text,
)
from paperorchestra.engine.reports import _record_validation_report, collect_paper_contract_issues
from paperorchestra.engine.schemas import REVIEW_SCHEMA
from paperorchestra.engine.section_scope import _expected_section_titles_from_outline
from paperorchestra.manuscript.latex import compile_latex_with_report
from paperorchestra.manuscript.narrative_artifacts import planning_artifact_status
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.citations import canonical_citation_keys
from paperorchestra.manuscript.figure_review_builder import build_figure_placement_review
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


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


def review_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    review_name: str = "review.latest.json",
    runtime_mode: str = "compatibility",
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before review.")
    paper_text = read_text(state.artifacts.paper_full_tex)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_paper_text = _prompt_compact_text(paper_text, head_chars=22000, tail_chars=4000)
    prompt_citation_map = _compact_citation_map_for_prompt(
        citation_map,
        include_abstract=False,
        include_authors=False,
        include_year=False,
        include_venue=False,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    user_prompt = f"""
{_data_block('paper.tex', prompt_paper_text)}

{_data_block('citation_map.json', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    avg_citation_count = max(1, len(canonical_citation_keys(citation_map)))
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_review_system(avg_citation_count=avg_citation_count), user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="reviewer",
        trace_stage="review",
        output_schema=REVIEW_SCHEMA,
            )
    payload = extract_json(response)
    payload.setdefault("schema_version", "paper-review/1")
    payload["manuscript_path"] = state.artifacts.paper_full_tex
    manuscript_sha = hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
    payload["manuscript_sha256"] = manuscript_sha
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
    )
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    path = review_path(cwd, review_name)
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="review",
        role="Reviewer Lane",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.paper_full_tex or ""],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
        lane_manifest_path=lane_path,
    )
    write_json(path, payload)
    state.artifacts.latest_review_json = str(path)
    score = float(payload.get("overall_score", 0.0))
    axes = _extract_axis_scores(payload)
    state.review_history.append(ScoreSnapshot(overall_score=score, raw_path=str(path), axes=axes))
    state.active_artifact = review_name
    state.notes.append(f"Paper reviewed: overall_score={score}")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def _extract_axis_scores(review_payload: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    axis_scores = review_payload.get("axis_scores", {})
    if isinstance(axis_scores, dict):
        for key, value in axis_scores.items():
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                result[key] = float(value["score"])
            elif isinstance(value, (int, float)):
                result[key] = float(value)
    return result

