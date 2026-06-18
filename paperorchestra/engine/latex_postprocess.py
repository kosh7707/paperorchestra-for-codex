from __future__ import annotations

import re
from typing import Any

from paperorchestra.engine.latex_plot_postprocess import (
    _ensure_generated_plot_usage,
    _escape_latex_text,
    _filter_plot_context_for_latex,
    _is_generated_placeholder_asset,
    _normalize_figure_token,
    _normalize_generated_plot_paths,
    _normalize_plot_context_key,
    _normalize_source_figure_paths,
    _reviewable_plot_assets_index,
    _reviewable_plot_manifest,
    _stabilize_figure_float_placement,
)
from paperorchestra.manuscript.citations import CITE_COMMAND_RE, allowed_citation_keys, extract_citation_keys


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
