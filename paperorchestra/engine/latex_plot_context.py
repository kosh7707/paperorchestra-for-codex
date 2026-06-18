from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _normalize_plot_context_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^fig(?:ure)?[:_\-\s]+", "", text)
    text = Path(text).stem if "/" in text or "\\" in text or "." in Path(text).name else text
    return re.sub(r"[^a-z0-9]+", "", text)


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


def _filter_plot_context_for_latex(
    latex: str | None,
    plot_manifest: dict[str, Any],
    plot_assets_index: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not latex:
        return {"figures": []}, {"assets": []}
    raw_refs: set[str] = set()
    for group in re.findall(r"\\(?:ref|autoref|cref|Cref|prettyref)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}", latex):
        raw_refs.update(part.strip() for part in group.split(",") if part.strip())
    raw_refs.update(token for token in re.findall(r"\\label\{([^}]+)\}", latex))
    referenced_tokens = {_normalize_plot_context_key(token) for token in raw_refs}
    included_raw = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", latex)
    included_raw.extend(re.findall(r"\\input\{([^}]+)\}", latex))
    included = {_normalize_plot_context_key(token) for token in included_raw}
    asset_matches: list[dict[str, Any]] = []
    figure_ids: set[str] = set()
    for asset in plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []:
        if not isinstance(asset, dict):
            continue
        asset_names = {
            _normalize_plot_context_key(asset.get(field))
            for field in ("filename", "latex_path", "latex_snippet_path")
            if asset.get(field)
        }
        fid = str(asset.get("figure_id") or "")
        fid_key = _normalize_plot_context_key(fid)
        if included & asset_names or (fid_key and fid_key in referenced_tokens):
            asset_matches.append(asset)
            if fid:
                figure_ids.add(fid_key)
    figure_matches = []
    for figure in plot_manifest.get("figures", []) if isinstance(plot_manifest, dict) else []:
        if not isinstance(figure, dict):
            continue
        fid = str(figure.get("figure_id") or "")
        fid_key = _normalize_plot_context_key(fid)
        if fid and (fid_key in figure_ids or fid_key in referenced_tokens or fid.lower() in latex.lower()):
            figure_matches.append(figure)
    return {**plot_manifest, "figures": figure_matches}, {**plot_assets_index, "assets": asset_matches}
