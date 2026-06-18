from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.figure_matching_keys import _high_signal_tokens
from paperorchestra.manuscript.figure_patterns import (
    DECORATIVE_VISUAL_RE as _DECORATIVE_VISUAL_RE,
    INCLUDE_GRAPHICS_RE,
    NONTECHNICAL_VISUAL_CONTEXT_RE as _NONTECHNICAL_VISUAL_CONTEXT_RE,
    NONTECHNICAL_VISUAL_STRONG_RE as _NONTECHNICAL_VISUAL_STRONG_RE,
    PROCESS_CAPTION_RE as _PROCESS_CAPTION_RE,
    UNRELATED_CAPTION_CUE_RE as _UNRELATED_CAPTION_CUE_RE,
)


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
