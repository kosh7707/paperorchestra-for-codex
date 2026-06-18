from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.engine.latex_generated_plot_usage import _ensure_generated_plot_usage
from paperorchestra.engine.latex_plot_filter import _filter_plot_context_for_latex
from paperorchestra.engine.latex_plot_generated_paths import _normalize_generated_plot_paths
from paperorchestra.engine.latex_plot_keys import _normalize_plot_context_key
from paperorchestra.engine.latex_plot_reviewable import (
    _is_generated_placeholder_asset,
    _reviewable_plot_assets_index,
    _reviewable_plot_manifest,
)
from paperorchestra.engine.latex_plot_text import (
    _escape_latex_text,
    _normalize_figure_token,
)
from paperorchestra.manuscript.citations import CITE_COMMAND_RE, allowed_citation_keys, extract_citation_keys


def _stabilize_figure_float_placement(latex: str) -> str:
    """Avoid top-only figure floats that LaTeX can defer to the manuscript tail."""

    def replace(match: re.Match[str]) -> str:
        env = match.group(1)
        placement = match.group(2)
        if placement is not None:
            normalized = placement.replace(" ", "")
            placement_flags = set(normalized.lower())
            if placement_flags & {"h", "b", "p"} or "H" in normalized:
                return match.group(0)
        stable = "!tbp" if env == "figure*" else "!htbp"
        return f"\\begin{{{env}}}[{stable}]"

    return re.sub(r"\\begin\{(figure\*?)\}(?:\[([^\]]*)\])?", replace, latex)


def _normalize_source_figure_paths(latex: str, figures_dir: str | Path | None) -> str:
    if not figures_dir:
        return latex
    path = Path(figures_dir)
    if not path.exists():
        return latex
    for figure_path in sorted(path.iterdir()):
        if figure_path.is_file():
            latex = _normalize_source_figure_path(latex, figure_path.name)
    return latex.replace("inputs/inputs/figures/", "inputs/figures/")


def _normalize_source_figure_path(latex: str, name: str) -> str:
    normalized = f"inputs/figures/{name}"
    for prefix in ["figures", "figs"]:
        latex = re.sub(rf"(?<!inputs/){re.escape(prefix)}/{re.escape(name)}", normalized, latex)
        latex = re.sub(rf"(?<!inputs\\){re.escape(prefix)}\\{re.escape(name)}", normalized, latex)
    return re.sub(
        rf"(\\includegraphics(?:\[[^\]]*\])?\{{)(?![^}}]*inputs/figures/){re.escape(name)}(\}})",
        lambda match: f"{match.group(1)}{normalized}{match.group(2)}",
        latex,
    )


def _ensure_bibliography_hook(latex: str, citation_map: dict[str, Any]) -> str:
    if not citation_map:
        return latex
    thebibliography_re = re.compile(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL | re.IGNORECASE)
    manual_match = thebibliography_re.search(latex)
    if manual_match:
        manual_block = manual_match.group(0)
        cited_keys = extract_citation_keys(latex[: manual_match.start()] + " " + latex[manual_match.end() :])
        missing_manual_keys = {key for key in cited_keys if key in citation_map} - set(
            re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", manual_block)
        )
        if not missing_manual_keys:
            return latex
        latex = thebibliography_re.sub("", latex, count=1)
    lowered = latex.lower()
    bibliography_re = re.compile(r"\\bibliography\s*\{[^}]*\}", re.IGNORECASE)
    if bibliography_re.search(latex):
        first_bibliography = True

        def _replace_bibliography(match: re.Match[str]) -> str:
            nonlocal first_bibliography
            if first_bibliography:
                first_bibliography = False
                return r"\bibliography{references}"
            return ""

        latex = bibliography_re.sub(_replace_bibliography, latex)
        if "\\bibliographystyle" not in lowered:
            latex = latex.replace(
                r"\bibliography{references}",
                "\\bibliographystyle{plain}\n\\bibliography{references}",
                1,
            )
        return latex
    hook = "\n\\bibliographystyle{plain}\n\\bibliography{references}\n"
    if "\\end{document}" in latex:
        return latex.replace("\\end{document}", hook + "\\end{document}")
    return latex + hook


def _drop_unknown_citation_keys(latex: str, citation_map: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Remove cite keys that are not present in the verified citation map."""

    if not citation_map:
        return latex, {}
    allowed = allowed_citation_keys(citation_map)
    dropped: dict[str, int] = {}

    def _replace(match: re.Match[str]) -> str:
        command = match.group(1)
        keys = [key.strip() for key in match.group(2).split(",") if key.strip()]
        kept = [key for key in keys if key in allowed]
        for key in keys:
            if key not in allowed:
                dropped[key] = dropped.get(key, 0) + 1
        if not kept:
            return ""
        return f"{command}{{{','.join(kept)}}}"

    return CITE_COMMAND_RE.sub(_replace, latex), dropped
