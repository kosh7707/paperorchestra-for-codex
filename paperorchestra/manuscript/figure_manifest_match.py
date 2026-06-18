from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.figure_candidate_keys import (
    _asset_is_reviewable,
    _asset_keys,
    _figure_keys,
    _plot_asset_candidates,
    _plot_manifest_candidates,
)
from paperorchestra.manuscript.figure_key_normalization import _high_signal_tokens, _normalize_figure_key


def _match_plot_manifest(
    *,
    label: str | None,
    caption: str,
    included_assets: list[str],
    plot_manifest: dict[str, Any] | None,
    plot_assets_index: dict[str, Any] | None,
) -> dict[str, Any] | None:
    assets = _plot_asset_candidates(plot_assets_index)
    figures = _plot_manifest_candidates(plot_manifest)
    if not assets and not figures:
        return None

    matched_assets = _matching_assets(included_assets, assets)
    matches, precedence = _matching_figures(label=label, caption=caption, matched_assets=matched_assets, figures=figures)
    if not matches:
        return None
    return _manifest_match_payload(matches, precedence=precedence, matched_asset=matched_assets[0] if matched_assets else None)


def _matching_assets(included_assets: list[str], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    included_keys = {_normalize_figure_key(name) for name in included_assets if name}
    return [asset for asset in assets if included_keys & _asset_keys(asset)]


def _matching_figures(
    *,
    label: str | None,
    caption: str,
    matched_assets: list[dict[str, Any]],
    figures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    matches = _asset_matched_figures(matched_assets, figures)
    if matches:
        return matches, "asset"
    if label:
        matches = _label_matched_figures(label, figures)
        if matches:
            return matches, "label"
    return _caption_token_matched_figures(caption, figures), "caption_tokens"


def _asset_matched_figures(matched_assets: list[dict[str, Any]], figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asset_figure_ids = {
        _normalize_figure_key(asset.get("figure_id"))
        for asset in matched_assets
        if isinstance(asset.get("figure_id"), str) and asset.get("figure_id")
    }
    return [figure for figure in figures if _figure_keys(figure) & asset_figure_ids]


def _label_matched_figures(label: str, figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label_ids = {_normalize_figure_key(label)}
    return [figure for figure in figures if _figure_keys(figure) & label_ids]


def _caption_token_matched_figures(caption: str, figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    caption_tokens = _high_signal_tokens(caption)
    return [
        figure
        for figure in figures
        if len(caption_tokens & _high_signal_tokens(figure.get("title"), figure.get("caption"), figure.get("purpose"), figure.get("objective"))) >= 2
    ]


def _manifest_match_payload(
    matches: list[dict[str, Any]],
    *,
    precedence: str,
    matched_asset: dict[str, Any] | None,
) -> dict[str, Any]:
    figure = matches[0]
    return {
        "status": "matched" if len(matches) == 1 else "ambiguous",
        "match_precedence": precedence,
        "figure_id": figure.get("figure_id") or figure.get("id") or figure.get("label"),
        "title": figure.get("title"),
        "purpose": figure.get("purpose") or figure.get("objective"),
        "caption": figure.get("caption"),
        "reviewable": _asset_is_reviewable(matched_asset),
        "asset": _matched_asset_payload(matched_asset),
        "candidate_count": len(matches),
    }


def _matched_asset_payload(matched_asset: dict[str, Any] | None) -> dict[str, Any] | None:
    if not matched_asset:
        return None
    return {
        key: matched_asset.get(key)
        for key in ("figure_id", "filename", "latex_path", "latex_snippet_path", "asset_kind", "review_status")
        if matched_asset.get(key)
    }
