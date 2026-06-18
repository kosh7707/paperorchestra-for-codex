from __future__ import annotations

from typing import Any


def _is_generated_placeholder_asset(asset: dict[str, Any]) -> bool:
    return asset.get("asset_kind") == "generated_placeholder" or asset.get("review_status") == "human_final_artwork_required"


def _reviewable_plot_assets_index(plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_assets_index, dict):
        return {"assets": []}
    return {
        **plot_assets_index,
        "assets": [
            asset
            for asset in plot_assets_index.get("assets", [])
            if isinstance(asset, dict) and not _is_generated_placeholder_asset(asset)
        ],
    }


def _reviewable_plot_manifest(plot_manifest: dict[str, Any] | None, plot_assets_index: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plot_manifest, dict):
        return {"figures": []}
    placeholder_ids = {
        str(asset.get("figure_id"))
        for asset in (plot_assets_index or {}).get("assets", [])
        if isinstance(asset, dict) and _is_generated_placeholder_asset(asset) and asset.get("figure_id")
    }
    if not placeholder_ids:
        return plot_manifest
    return {
        **plot_manifest,
        "figures": [
            figure
            for figure in plot_manifest.get("figures", [])
            if not (isinstance(figure, dict) and str(figure.get("figure_id") or "") in placeholder_ids)
        ],
    }
