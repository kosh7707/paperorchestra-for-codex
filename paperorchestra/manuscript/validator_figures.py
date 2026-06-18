from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.manuscript.validation_types import ValidationIssue


def check_figure_file_coverage(latex: str, figures_dir: str | None) -> list[ValidationIssue]:
    if not figures_dir:
        return []
    figure_dir_path = Path(figures_dir)
    required_figure_names = [path.name for path in figure_dir_path.iterdir() if path.is_file() and not path.name.startswith(".")]
    missing_figures = [name for name in required_figure_names if name not in latex]
    if not missing_figures:
        return []
    return [
        ValidationIssue(
            code="figure_file_not_referenced",
            severity="warning",
            message=f"Provided figures not referenced in LaTeX: {', '.join(missing_figures)}",
        )
    ]


def check_plot_plan_coverage(latex: str, plot_manifest: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_manifest:
        return []
    lowered_latex = latex.lower()
    missing_plot_coverage = []
    for figure in plot_manifest.get("figures", []):
        figure_id = figure.get("figure_id", "")
        title = figure.get("title", "")
        caption = figure.get("caption", "")
        if figure_id and figure_id.lower() in lowered_latex:
            continue
        if title and title.lower() in lowered_latex:
            continue
        if caption and caption.lower() in lowered_latex:
            continue
        if figure_id:
            missing_plot_coverage.append(figure_id)
    if not missing_plot_coverage:
        return []
    return [
        ValidationIssue(
            code="plot_plan_not_reflected",
            severity="error",
            message="Plot-plan figures are not represented in the manuscript: " + ", ".join(sorted(missing_plot_coverage)),
        )
    ]


def check_generated_plot_asset_usage(latex: str, plot_assets_index: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_assets_index:
        return []
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    missing_assets = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_kind") == "generated_placeholder" or asset.get("review_status") == "human_final_artwork_required":
            continue
        filename = asset.get("filename")
        snippet_path = asset.get("latex_snippet_path")
        latex_path = asset.get("latex_path")
        if isinstance(snippet_path, str) and snippet_path and snippet_path in latex:
            continue
        if isinstance(latex_path, str) and latex_path and latex_path in latex:
            continue
        if isinstance(filename, str) and filename and filename in latex:
            continue
        if isinstance(filename, str) and filename:
            missing_assets.append(filename)
    if not missing_assets:
        return []
    return [
        ValidationIssue(
            code="generated_plot_asset_not_used",
            severity="warning",
            message="Generated plot assets are not referenced in the manuscript: " + ", ".join(sorted(missing_assets)),
        )
    ]
