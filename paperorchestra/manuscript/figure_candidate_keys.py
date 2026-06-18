from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.manuscript.figure_key_normalization import _normalize_figure_key


def _plot_asset_candidates(plot_assets_index: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plot_assets_index, dict):
        return []
    return [asset for asset in plot_assets_index.get("assets") or [] if isinstance(asset, dict)]


def _plot_manifest_candidates(plot_manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plot_manifest, dict):
        return []
    return [figure for figure in plot_manifest.get("figures") or [] if isinstance(figure, dict)]


def _asset_is_reviewable(asset: dict[str, Any] | None) -> bool:
    if not isinstance(asset, dict):
        return True
    return not (
        asset.get("asset_kind") == "generated_placeholder"
        or asset.get("review_status") == "human_final_artwork_required"
    )


def _figure_keys(figure: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ("figure_id", "id", "label"):
        value = figure.get(field)
        if isinstance(value, str) and value.strip():
            keys.add(_normalize_figure_key(value))
    return {key for key in keys if key}


def _asset_keys(asset: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ("filename", "latex_path", "latex_snippet_path"):
        value = asset.get(field)
        if isinstance(value, str) and value.strip():
            keys.add(_normalize_figure_key(value))
            keys.add(_normalize_figure_key(Path(value).name))
    if asset.get("figure_id"):
        keys.add(_normalize_figure_key(asset.get("figure_id")))
    return {key for key in keys if key}
