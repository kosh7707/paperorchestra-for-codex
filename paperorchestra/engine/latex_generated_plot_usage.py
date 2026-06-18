from __future__ import annotations

from typing import Any

from paperorchestra.engine.latex_plot_context import _is_generated_placeholder_asset
from paperorchestra.engine.latex_plot_text import _escape_latex_text
from paperorchestra.manuscript.structure import _insert_block_into_section, _preferred_section_name


def _ensure_generated_plot_usage(latex: str, plot_assets_index: dict[str, Any]) -> str:
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    rendered = latex
    for asset in assets:
        if not isinstance(asset, dict) or _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        title = asset.get("title", "")
        caption = asset.get("caption", title)
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        filename = asset.get("filename", "")
        label_present = bool(figure_id and f"\\label{{{figure_id}}}" in rendered)
        asset_present = any(token and token in rendered for token in [snippet_path, filename])
        escaped_caption = _escape_latex_text(caption) if isinstance(caption, str) else ""
        caption_present = bool(
            escaped_caption and (f"\\caption{{{escaped_caption}}}" in rendered or f"\\caption{{{caption}}}" in rendered)
        )
        if label_present or asset_present or caption_present:
            continue
        include = (
            f"\\input{{{snippet_path}}}"
            if isinstance(snippet_path, str) and snippet_path.endswith(".tex")
            else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        )
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[!htbp]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        section_name = _preferred_section_name(
            rendered,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
        rendered = _insert_block_into_section(
            rendered,
            section_name=section_name,
            block=block,
            label=figure_id,
            anchor_tokens=[title, caption, figure_id.replace("_", " ")],
        )
    return rendered
