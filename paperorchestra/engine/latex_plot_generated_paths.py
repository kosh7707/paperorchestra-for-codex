from __future__ import annotations

import re
from typing import Any

from paperorchestra.engine.latex_plot_assets import asset_by_normalized_label, asset_candidate_paths, reviewable_plot_assets
from paperorchestra.engine.latex_plot_figure_blocks import rewrite_generated_figure_block
from paperorchestra.manuscript.figure_patterns import FIGURE_ENV_RE


def _normalize_generated_plot_paths(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = reviewable_plot_assets(plot_assets_index)
    for asset in assets:
        latex = _rewrite_asset_path_references(latex, asset)
    by_label = asset_by_normalized_label(assets)
    return FIGURE_ENV_RE.sub(lambda match: rewrite_generated_figure_block(match, by_label), latex)


def _rewrite_asset_path_references(latex: str, asset: dict[str, Any]) -> str:
    snippet_path = asset.get("latex_snippet_path")
    if not isinstance(snippet_path, str):
        return latex
    for candidate in asset_candidate_paths(asset):
        latex = latex.replace(candidate, snippet_path)
    if snippet_path.endswith(".tex"):
        for candidate in [snippet_path, *asset_candidate_paths(asset)]:
            latex = _replace_includegraphics_exact(latex, candidate, snippet_path)
    latex = _rewrite_filename_references(latex, asset, snippet_path)
    return _rewrite_figure_id_references(latex, asset, snippet_path)


def _replace_includegraphics_exact(latex: str, candidate: str, snippet_path: str) -> str:
    if not candidate:
        return latex
    return re.sub(
        rf"\\includegraphics(?:\[[^\]]*\])?\{{{re.escape(candidate)}\}}",
        lambda _: f"\\input{{{snippet_path}}}",
        latex,
    )


def _rewrite_filename_references(latex: str, asset: dict[str, Any], snippet_path: str) -> str:
    filename = asset.get("filename")
    if not isinstance(filename, str) or not filename:
        return latex
    latex = re.sub(
        rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(filename)}\}}",
        lambda _: f"\\input{{{snippet_path}}}",
        latex,
    )
    for candidate in [filename, f"build/plot-assets/{filename}", f"./build/plot-assets/{filename}"]:
        latex = latex.replace(candidate, snippet_path)
    return latex


def _rewrite_figure_id_references(latex: str, asset: dict[str, Any], snippet_path: str) -> str:
    figure_id = asset.get("figure_id")
    if not isinstance(figure_id, str) or not figure_id:
        return latex
    return re.sub(
        rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(figure_id)}\.(?:pdf|png|svg|jpg|jpeg)\}}",
        lambda _: f"\\input{{{snippet_path}}}",
        latex,
    )
