from __future__ import annotations

from typing import Any

from paperorchestra.engine.latex_postprocess import _escape_latex_text, _is_generated_placeholder_asset
from paperorchestra.manuscript.structure import _insert_block_into_section, _preferred_section_name
from paperorchestra.manuscript.validation_types import ValidationIssue


def _missing_plot_ids(issues: list[ValidationIssue]) -> list[str]:
    prefix = "Plot-plan figures are not represented in the manuscript:"
    missing: list[str] = []
    for issue in issues:
        if issue.code != "plot_plan_not_reflected":
            continue
        if prefix in issue.message:
            suffix = issue.message.split(prefix, 1)[1]
            missing.extend(part.strip() for part in suffix.split(",") if part.strip())
    return sorted(set(missing))


def _inject_missing_plot_assets(
    latex: str,
    issues: list[ValidationIssue],
    plot_assets_index: dict[str, Any] | None,
) -> str:
    missing_ids = set(_missing_plot_ids(issues))
    if not missing_ids or not isinstance(plot_assets_index, dict):
        return latex
    rendered = latex
    for asset in plot_assets_index.get("assets", []):
        if not isinstance(asset, dict) or _is_generated_placeholder_asset(asset):
            continue
        figure_id = asset.get("figure_id", "")
        if figure_id not in missing_ids:
            continue
        snippet_path = asset.get("latex_snippet_path") or asset.get("latex_path")
        title = asset.get("title", figure_id)
        caption = asset.get("caption", title)
        include = f"\\input{{{snippet_path}}}" if isinstance(snippet_path, str) and snippet_path.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{snippet_path}}}"
        block = (
            f"\n% PaperOrchestra:auto-repaired figure:{figure_id}\n"
            "\\begin{figure}[!htbp]\n"
            f"{include}\n"
            f"\\caption{{{_escape_latex_text(caption)}}}\n"
            f"\\label{{{figure_id}}}\n"
            "\\end{figure}\n"
        )
        anchors = [title, caption, figure_id.replace("_", " ")]
        rendered = _insert_block_into_section(
            rendered,
            section_name=_preferred_section_name(rendered, label=figure_id, anchor_tokens=anchors),
            block=block,
            label=figure_id,
            anchor_tokens=anchors,
        )
    return rendered
