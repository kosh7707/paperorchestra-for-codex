from __future__ import annotations

import re
from typing import Any

from paperorchestra.engine.latex_plot_text import _normalize_figure_token
from paperorchestra.manuscript.figure_patterns import LABEL_RE


def rewrite_generated_figure_block(match: re.Match[str], asset_by_label: dict[str, dict[str, Any]]) -> str:
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
    replaced = _replace_first_graphics_or_input(body, _include_command(snippet_path))
    if replaced == body:
        return match.group(0)
    placement_suffix = f"[{placement}]" if placement else ""
    return f"\\begin{{{env}}}{placement_suffix}{replaced}\\end{{{env}}}"


def _include_command(snippet_path: str) -> str:
    if snippet_path.endswith(".tex"):
        return f"\\input{{{snippet_path}}}"
    return f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"


def _replace_first_graphics_or_input(body: str, include: str) -> str:
    replaced = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", lambda _: include, body, count=1)
    if replaced == body:
        replaced = re.sub(r"\\input\{[^}]+\}", lambda _: include, body, count=1)
    return replaced
