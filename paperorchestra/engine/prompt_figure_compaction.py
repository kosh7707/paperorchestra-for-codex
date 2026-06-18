from __future__ import annotations

from typing import Any

from paperorchestra.engine.prompt_markup import _prompt_compact_text


def _compact_plot_manifest_for_prompt(plot_manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return plot_manifest
    figures = []
    for figure in plot_manifest.get("figures", [])[:8]:
        if not isinstance(figure, dict):
            continue
        figures.append(
            {
                "figure_id": figure.get("figure_id"),
                "title": _prompt_compact_text(str(figure.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(figure.get("caption") or ""), head_chars=180, tail_chars=0),
                "plot_type": figure.get("plot_type"),
                "aspect_ratio": figure.get("aspect_ratio"),
            }
        )
    return {"figures": figures}


def _compact_plot_assets_for_prompt(plot_assets_index: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return plot_assets_index
    assets = []
    for asset in plot_assets_index.get("assets", [])[:8]:
        if not isinstance(asset, dict):
            continue
        assets.append(
            {
                "figure_id": asset.get("figure_id"),
                "title": _prompt_compact_text(str(asset.get("title") or ""), head_chars=120, tail_chars=0),
                "caption": _prompt_compact_text(str(asset.get("caption") or ""), head_chars=180, tail_chars=0),
                "filename": asset.get("filename"),
                "latex_snippet_path": asset.get("latex_snippet_path"),
                "plot_type": asset.get("plot_type"),
            }
        )
    return {"assets": assets}
