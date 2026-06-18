from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.reviews.fidelity_types import FidelityCheck


def _plot_generation_check(state: SessionState) -> FidelityCheck:
    plot_status = "missing"
    if state.artifacts.plot_manifest_json and state.artifacts.plot_captions_json:
        plot_status = "partial"
        if state.artifacts.plot_assets_json and Path(state.artifacts.plot_assets_json).exists():
            try:
                assets_payload = read_json(state.artifacts.plot_assets_json)
                if assets_payload.get("assets", []):
                    plot_status = "implemented"
            except Exception:
                plot_status = "partial"
        elif state.inputs.figures_dir and Path(state.inputs.figures_dir).exists() and any(Path(state.inputs.figures_dir).iterdir()):
            plot_status = "implemented"
    return FidelityCheck(
        code="plot_generation_depth",
        status=plot_status,
        rationale="The paper includes a dedicated Plot Generation stage with visual artifacts and captions, not only planning text.",
    )


def _plot_usage_check(state: SessionState) -> FidelityCheck:
    plot_usage_status = "missing"
    if state.artifacts.plot_assets_json and Path(state.artifacts.plot_assets_json).exists() and state.artifacts.paper_full_tex:
        plot_usage_status = "partial"
        try:
            assets_payload = read_json(state.artifacts.plot_assets_json)
            latex_text = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
            asset_references = [
                asset.get("latex_snippet_path") or asset.get("latex_path") or asset.get("filename")
                for asset in assets_payload.get("assets", [])
                if isinstance(asset, dict) and isinstance(asset.get("filename"), str)
            ]
            if asset_references and all(reference in latex_text for reference in asset_references):
                plot_usage_status = "implemented"
        except Exception:
            plot_usage_status = "partial"
    return FidelityCheck(
        code="generated_plot_assets_used_in_manuscript",
        status=plot_usage_status,
        rationale="Generated plot assets should be referenced directly in the manuscript, not only stored as side artifacts.",
    )


def _section_writing_check(state: SessionState) -> FidelityCheck:
    writing_status = "missing"
    if state.artifacts.intro_related_tex and state.artifacts.paper_full_tex:
        writing_status = "implemented"
    elif state.artifacts.paper_full_tex:
        writing_status = "partial"
    return FidelityCheck(
        code="section_writing_pipeline",
        status=writing_status,
        rationale="The paper first drafts Introduction/Related Work from verified citations and then completes the remaining sections.",
    )


def _iterative_refinement_check(state: SessionState) -> FidelityCheck:
    refinement_status = "missing"
    if state.review_history:
        refinement_status = "partial"
        if state.refinement_iteration > 0:
            refinement_status = "implemented"
    return FidelityCheck(
        code="iterative_refinement_gate",
        status=refinement_status,
        rationale="The paper's refinement loop accepts revisions only on non-regressive review outcomes.",
    )
