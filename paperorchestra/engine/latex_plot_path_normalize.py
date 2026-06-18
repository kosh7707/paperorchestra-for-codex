from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.engine.latex_plot_context import _is_generated_placeholder_asset
from paperorchestra.engine.latex_plot_text import _normalize_figure_token
from paperorchestra.manuscript.figure_patterns import FIGURE_ENV_RE, LABEL_RE


def _normalize_generated_plot_paths(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    asset_by_label: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            asset_by_label[_normalize_figure_token(figure_id)] = asset
        snippet_path = asset.get("latex_snippet_path")
        if not isinstance(snippet_path, str):
            continue
        filename = asset.get("filename")
        candidates: list[str] = []
        for key in ["path", "tex_path", "latex_path", "latex_snippet_path"]:
            candidate = asset.get(key)
            if isinstance(candidate, str) and candidate:
                candidates.append(candidate)
                latex = latex.replace(candidate, snippet_path)
        if snippet_path.endswith(".tex"):
            for candidate in [snippet_path, *candidates]:
                if not candidate:
                    continue
                latex = re.sub(
                    rf"\\includegraphics(?:\[[^\]]*\])?\{{{re.escape(candidate)}\}}",
                    rf"\\input{{{snippet_path}}}",
                    latex,
                )
        if isinstance(filename, str) and filename:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(filename)}\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )
            for candidate in [filename, f"build/plot-assets/{filename}", f"./build/plot-assets/{filename}"]:
                latex = latex.replace(candidate, snippet_path)
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            latex = re.sub(
                rf"\\includegraphics(?:\[[^\]]*\])?\{{[^}}]*{re.escape(figure_id)}\.(?:pdf|png|svg|jpg|jpeg)\}}",
                rf"\\input{{{snippet_path}}}",
                latex,
            )

    def _rewrite_figure_block(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2) or ""
        body = match.group(3)
        label_match = LABEL_RE.search(body)
        if not label_match:
            return match.group(0)
        asset = asset_by_label.get(_normalize_figure_token(label_match.group(1)))
        if not asset:
            return match.group(0)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        if not isinstance(snippet_path, str) or not snippet_path:
            return match.group(0)
        include = (
            f"\\input{{{snippet_path}}}"
            if snippet_path.endswith(".tex")
            else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        )
        replaced = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", lambda _: include, body, count=1)
        if replaced == body:
            replaced = re.sub(r"\\input\{[^}]+\}", lambda _: include, body, count=1)
        if replaced == body:
            return match.group(0)
        placement_suffix = f"[{placement}]" if placement else ""
        return f"\\begin{{{env}}}{placement_suffix}{replaced}\\end{{{env}}}"

    return FIGURE_ENV_RE.sub(_rewrite_figure_block, latex)


def _normalize_source_figure_paths(latex: str, figures_dir: str | None) -> str:
    if not figures_dir:
        return latex
    path = Path(figures_dir)
    if not path.exists():
        return latex
    for figure_path in sorted(path.iterdir()):
        if not figure_path.is_file():
            continue
        name = figure_path.name
        normalized = f"inputs/figures/{name}"
        for prefix in ["figures", "figs"]:
            latex = re.sub(rf"(?<!inputs/){re.escape(prefix)}/{re.escape(name)}", normalized, latex)
            latex = re.sub(rf"(?<!inputs\\){re.escape(prefix)}\\{re.escape(name)}", normalized, latex)
        latex = re.sub(
            rf"(\\includegraphics(?:\[[^\]]*\])?\{{)(?![^}}]*inputs/figures/){re.escape(name)}(\}})",
            rf"\1{normalized}\2",
            latex,
        )
    return latex.replace("inputs/inputs/figures/", "inputs/figures/")
