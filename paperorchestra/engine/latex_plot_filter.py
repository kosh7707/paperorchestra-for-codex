from __future__ import annotations

import re
from typing import Any

from paperorchestra.engine.latex_plot_keys import _normalize_plot_context_key


def _filter_plot_context_for_latex(
    latex: str | None,
    plot_manifest: dict[str, Any],
    plot_assets_index: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not latex:
        return {"figures": []}, {"assets": []}
    referenced_tokens = _referenced_plot_tokens(latex)
    included = _included_plot_tokens(latex)
    asset_matches: list[dict[str, Any]] = []
    figure_ids: set[str] = set()
    for asset in plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []:
        if not isinstance(asset, dict):
            continue
        asset_names = _asset_names(asset)
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


def _referenced_plot_tokens(latex: str) -> set[str]:
    raw_refs: set[str] = set()
    for group in re.findall(r"\\(?:ref|autoref|cref|Cref|prettyref)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}", latex):
        raw_refs.update(part.strip() for part in group.split(",") if part.strip())
    raw_refs.update(token for token in re.findall(r"\\label\{([^}]+)\}", latex))
    return {_normalize_plot_context_key(token) for token in raw_refs}


def _included_plot_tokens(latex: str) -> set[str]:
    included_raw = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", latex)
    included_raw.extend(re.findall(r"\\input\{([^}]+)\}", latex))
    return {_normalize_plot_context_key(token) for token in included_raw}


def _asset_names(asset: dict[str, Any]) -> set[str]:
    return {
        _normalize_plot_context_key(asset.get(field))
        for field in ("filename", "latex_path", "latex_snippet_path")
        if asset.get(field)
    }
