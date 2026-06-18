from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, read_json, write_json
from paperorchestra.core.session import artifact_path, build_path, load_session, save_session
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _lane_owner
from paperorchestra.engine.latex_postprocess import _escape_latex_text, _is_generated_placeholder_asset
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text, _read_inputs
from paperorchestra.engine.research_discovery import _build_candidate_payload, _write_candidate_artifacts
from paperorchestra.engine.schemas import PLOT_SCHEMA, validate_plot_manifest
from paperorchestra.manuscript.plot_assets import render_plot_assets
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.structure import _insert_block_into_section, _preferred_section_name
from paperorchestra.manuscript.validator import ValidationIssue
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def _fallback_plot_manifest(outline: dict[str, Any]) -> dict[str, Any]:
    figures = []
    for plot in outline.get("plotting_plan", []):
        figures.append(
            {
                "figure_id": plot["figure_id"],
                "title": plot["title"],
                "plot_type": plot["plot_type"],
                "data_source": plot["data_source"],
                "objective": plot["objective"],
                "aspect_ratio": plot["aspect_ratio"],
                "rendering_brief": plot["objective"],
                "caption": plot["title"],
                "source_fidelity_notes": f"{plot['data_source']}: fallback manifest without model-authored caption.",
            }
        )
    return {"figures": figures}


def _build_plot_payload(outline: dict[str, Any], state, provider: BaseProvider | None, *, runtime_mode: str = "compatibility", cwd: str | Path | None = None) -> tuple[dict[str, Any], str, bool, list[str]]:
    inputs = _read_inputs(state)
    if provider is None:
        return _fallback_plot_manifest(outline), "python", True, ["No provider available; fallback manifest used."]
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=5000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=12000, tail_chars=3000)
    user_prompt = f"""
{_data_block('plotting_plan', json.dumps(outline['plotting_plan'], indent=2, ensure_ascii=False))}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.plot_system, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="team",
        trace_stage="plot",
        output_schema=PLOT_SCHEMA,
    )
    return extract_json(response), lane_type, fallback_used, lane_notes


def _write_plot_artifacts(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    validate_plot_manifest(payload)
    manifest_path = artifact_path(cwd, "plot_manifest.json")
    captions_path = artifact_path(cwd, "plot_captions.json")
    write_json(manifest_path, payload)
    write_json(captions_path, {item["figure_id"]: item["caption"] for item in payload["figures"]})
    return manifest_path, captions_path


def _write_plot_assets(cwd: str | Path | None, payload: dict[str, Any]) -> tuple[Path, Path]:
    assets_dir = build_path(cwd, "plot-assets")
    output_dir, index_path = render_plot_assets(payload, assets_dir)
    return output_dir, index_path


def run_parallel_plot_and_literature(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    discovery_mode: str = "model",
    runtime_mode: str = "compatibility",
) -> dict[str, str]:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before running parallel plot/literature phase.")
    outline = read_json(state.artifacts.outline_json)
    plot_provider = provider.fork()
    discovery_provider = provider.fork()
    with ThreadPoolExecutor(max_workers=2) as executor:
        plots_future = executor.submit(_build_plot_payload, outline, state, plot_provider, runtime_mode=runtime_mode, cwd=cwd)
        candidates_future = executor.submit(
            _build_candidate_payload,
            outline,
            state,
            discovery_provider if discovery_mode == "model" else None,
            discovery_mode,
            runtime_mode=runtime_mode,
            cwd=cwd,
        )
        plot_payload, plot_lane_type, plot_fallback_used, plot_lane_notes = plots_future.result()
        candidate_payload, literature_lane_type, literature_fallback_used, literature_lane_notes = candidates_future.result()

    manifest_path, captions_path = _write_plot_artifacts(cwd, plot_payload)
    assets_dir, assets_index = _write_plot_assets(cwd, plot_payload)
    candidate_path = _write_candidate_artifacts(cwd, candidate_payload)

    plot_lane_path = record_lane_manifest(
        cwd,
        stage="plot",
        role="Plotting Agent",
        runtime_mode=runtime_mode,
        lane_type=plot_lane_type,
        owner=_lane_owner(plot_lane_type, plot_fallback_used),
        status="fallback_completed" if plot_fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(manifest_path), str(captions_path), str(assets_index)],
        fallback_used=plot_fallback_used,
        notes=plot_lane_notes,
    )
    literature_lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=literature_lane_type,
        owner=_lane_owner(literature_lane_type, literature_fallback_used),
        status="fallback_completed" if literature_fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(candidate_path)],
        fallback_used=literature_fallback_used,
        notes=literature_lane_notes,
    )

    state = load_session(cwd)
    state.artifacts.plot_manifest_json = str(manifest_path)
    state.artifacts.plot_captions_json = str(captions_path)
    state.artifacts.plot_assets_dir = str(assets_dir)
    state.artifacts.plot_assets_json = str(assets_index)
    state.artifacts.candidate_papers_json = str(candidate_path)
    state.current_phase = "literature_review"
    state.active_artifact = candidate_path.name
    state.latest_discovery_mode = discovery_mode
    state.notes.append("Plot Generation and Literature Review planning completed in parallel.")
    state.notes.append(f"Lane manifests recorded: {plot_lane_path.name}, {literature_lane_path.name}")
    save_session(cwd, state)

    return {
        "plots": str(manifest_path),
        "plot_captions": str(captions_path),
        "plot_assets": str(assets_index),
        "candidates": str(candidate_path),
    }


def _missing_plot_ids(issues: list[ValidationIssue]) -> list[str]:
    prefix = "Plot-plan figures are not represented in the manuscript:"
    missing: list[str] = []
    for issue in issues:
        if issue.code != "plot_plan_not_reflected":
            continue
        if prefix in issue.message:
            suffix = issue.message.split(prefix, 1)[1]
            missing.extend(part.strip() for part in suffix.split(",") if part.strip())
    return sorted(set(missing))


def _inject_missing_plot_assets(
    latex: str,
    issues: list[ValidationIssue],
    plot_assets_index: dict[str, Any] | None,
) -> str:
    missing_ids = set(_missing_plot_ids(issues))
    if not missing_ids or not isinstance(plot_assets_index, dict):
        return latex
    assets = plot_assets_index.get("assets", [])
    rendered = latex
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        if figure_id not in missing_ids:
            continue
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        title = asset.get("title", figure_id)
        caption = asset.get("caption", title)
        include = f"\\input{{{snippet_path}}}" if isinstance(snippet_path, str) and snippet_path.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[!htbp]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        section_name = _preferred_section_name(
            rendered,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
        rendered = _insert_block_into_section(
            rendered,
            section_name=section_name,
            block=block,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
    return rendered


def generate_plots(cwd: str | Path | None, provider: BaseProvider | None = None, *, runtime_mode: str = "compatibility") -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before generate-plots.")
    outline = read_json(state.artifacts.outline_json)
    payload, lane_type, fallback_used, lane_notes = _build_plot_payload(
        outline,
        state,
        provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
    )

    validate_plot_manifest(payload)
    manifest_path = artifact_path(cwd, "plot_manifest.json")
    captions_path = artifact_path(cwd, "plot_captions.json")
    write_json(manifest_path, payload)
    write_json(captions_path, {item["figure_id"]: item["caption"] for item in payload["figures"]})
    assets_dir, assets_index = _write_plot_assets(cwd, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="plot",
        role="Plotting Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(manifest_path), str(captions_path), str(assets_index)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.plot_manifest_json = str(manifest_path)
    state.artifacts.plot_captions_json = str(captions_path)
    state.artifacts.plot_assets_dir = str(assets_dir)
    state.artifacts.plot_assets_json = str(assets_index)
    state.current_phase = "literature_review"
    state.active_artifact = "plot_manifest.json"
    state.notes.append(f"Plot manifest and SVG assets generated for {len(payload['figures'])} figures.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return manifest_path

