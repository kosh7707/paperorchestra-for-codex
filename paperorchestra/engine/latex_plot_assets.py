from __future__ import annotations

from typing import Any

from paperorchestra.engine.latex_plot_reviewable import _is_generated_placeholder_asset
from paperorchestra.engine.latex_plot_text import _normalize_figure_token


def reviewable_plot_assets(plot_assets_index: dict[str, Any]) -> list[dict[str, Any]]:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    return [asset for asset in assets if isinstance(asset, dict) and not _is_generated_placeholder_asset(asset)]


def asset_by_normalized_label(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_label: dict[str, dict[str, Any]] = {}
    for asset in assets:
        figure_id = asset.get("figure_id")
        if isinstance(figure_id, str) and figure_id:
            by_label[_normalize_figure_token(figure_id)] = asset
    return by_label


def asset_candidate_paths(asset: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ["path", "tex_path", "latex_path", "latex_snippet_path"]:
        candidate = asset.get(key)
        if isinstance(candidate, str) and candidate:
            candidates.append(candidate)
    return candidates
