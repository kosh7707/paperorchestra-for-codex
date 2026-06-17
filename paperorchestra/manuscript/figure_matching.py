from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.figure_patterns import (
    DECORATIVE_VISUAL_RE as _DECORATIVE_VISUAL_RE,
    INCLUDE_GRAPHICS_RE,
    NONTECHNICAL_VISUAL_CONTEXT_RE as _NONTECHNICAL_VISUAL_CONTEXT_RE,
    NONTECHNICAL_VISUAL_STRONG_RE as _NONTECHNICAL_VISUAL_STRONG_RE,
    PROCESS_CAPTION_RE as _PROCESS_CAPTION_RE,
    UNRELATED_CAPTION_CUE_RE as _UNRELATED_CAPTION_CUE_RE,
)

_HIGH_SIGNAL_STOPWORDS = {
    "figure",
    "plot",
    "panel",
    "overview",
    "result",
    "results",
    "analysis",
    "comparison",
    "performance",
    "benchmark",
    "experiment",
    "stage",
    "across",
    "system",
    "method",
    "data",
    "model",
    "show",
    "shows",
    "summarize",
    "summarizes",
    "summary",
    "visual",
    "asset",
    "workflow",
}


def _normalize_figure_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^fig(?:ure)?[:_\-\s]+", "", text)
    text = Path(text).stem if "/" in text or "\\" in text or "." in Path(text).name else text
    return re.sub(r"[^a-z0-9]+", "", text)


def _high_signal_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", str(value or "").lower()):
            normalized = token.replace("_", "").replace("-", "")
            if normalized and normalized not in _HIGH_SIGNAL_STOPWORDS:
                tokens.add(normalized)
    return tokens


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

    included_keys = {_normalize_figure_key(name) for name in included_assets if name}
    matched_assets = [asset for asset in assets if included_keys & _asset_keys(asset)]
    asset_figure_ids = {
        _normalize_figure_key(asset.get("figure_id"))
        for asset in matched_assets
        if isinstance(asset.get("figure_id"), str) and asset.get("figure_id")
    }
    matches = [figure for figure in figures if _figure_keys(figure) & asset_figure_ids]
    precedence = "asset"
    if not matches and label:
        label_ids = {_normalize_figure_key(label)}
        matches = [figure for figure in figures if _figure_keys(figure) & label_ids]
        precedence = "label"
    if not matches:
        caption_tokens = _high_signal_tokens(caption)
        matches = [
            figure
            for figure in figures
            if len(caption_tokens & _high_signal_tokens(figure.get("title"), figure.get("caption"), figure.get("purpose"), figure.get("objective"))) >= 2
        ]
        precedence = "caption_tokens"
    if not matches:
        return None
    status = "matched" if len(matches) == 1 else "ambiguous"
    figure = matches[0]
    matched_asset = matched_assets[0] if matched_assets else None
    return {
        "status": status,
        "match_precedence": precedence,
        "figure_id": figure.get("figure_id") or figure.get("id") or figure.get("label"),
        "title": figure.get("title"),
        "purpose": figure.get("purpose") or figure.get("objective"),
        "caption": figure.get("caption"),
        "reviewable": _asset_is_reviewable(matched_asset),
        "asset": {
            key: matched_asset.get(key)
            for key in ("figure_id", "filename", "latex_path", "latex_snippet_path", "asset_kind", "review_status")
            if isinstance(matched_asset, dict) and matched_asset.get(key)
        }
        if matched_asset
        else None,
        "candidate_count": len(matches),
    }


def _caption_manifest_relation(caption: str, manifest_match: dict[str, Any] | None) -> str:
    if not manifest_match or manifest_match.get("status") != "matched" or not manifest_match.get("reviewable", True):
        return "not_applicable"
    manifest_tokens = _high_signal_tokens(
        manifest_match.get("purpose"),
        manifest_match.get("title"),
        manifest_match.get("caption"),
        manifest_match.get("figure_id"),
    )
    caption_tokens = _high_signal_tokens(caption)
    if _UNRELATED_CAPTION_CUE_RE.search(caption or "") and len(manifest_tokens & caption_tokens) < 2:
        return "mismatch"
    if len(manifest_tokens) < 3 or len(caption_tokens) < 3:
        return "insufficient_signal"
    if manifest_tokens & caption_tokens:
        return "matched"
    if (
        _PROCESS_CAPTION_RE.search(caption or "")
        or _UNRELATED_CAPTION_CUE_RE.search(caption or "")
        or _NONTECHNICAL_VISUAL_CONTEXT_RE.search(caption or "")
        or _DECORATIVE_VISUAL_RE.search(caption or "")
    ):
        return "mismatch"
    return "uncertain"


def _included_asset_names(body: str) -> list[str]:
    names = [match.group(1).strip() for match in INCLUDE_GRAPHICS_RE.finditer(body)]
    names.extend(match.group(1).strip() for match in re.finditer(r"\\input\{([^}]+)\}", body))
    return names


def _body_figure_has_nontechnical_asset(body: str, caption: str) -> bool:
    haystacks = [Path(name).stem.replace("-", " ").replace("_", " ") for name in _included_asset_names(body)]
    haystacks.append(caption)
    text = " ".join(haystacks)
    return bool(
        _NONTECHNICAL_VISUAL_STRONG_RE.search(text)
        or _NONTECHNICAL_VISUAL_CONTEXT_RE.search(text)
        or _DECORATIVE_VISUAL_RE.search(text)
    )


def _caption_has_process_or_placeholder_text(caption: str) -> bool:
    return bool(_PROCESS_CAPTION_RE.search(caption or ""))
