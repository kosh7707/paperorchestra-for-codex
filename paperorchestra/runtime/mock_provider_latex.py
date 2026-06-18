from __future__ import annotations

from paperorchestra.runtime.mock_provider_blocks import (
    extract_citation_keys,
    extract_metric_tokens,
    extract_plot_asset_paths,
    extract_plot_ids,
)
from paperorchestra.runtime.provider_base import CompletionRequest

MOCK_METHOD_BODY = (
    "The pipeline follows staged orchestration and references Figure~\\ref{{{plot_id}}}. "
    "The method section is intentionally non-empty in the mock provider so validation exercises "
    "a complete manuscript shape: it describes how inputs are converted into an outline, how plot "
    "and literature lanes produce artifacts, and how later writing stages consume those artifacts."
)


def _figure_body(asset_filename: str | None) -> str:
    if not asset_filename:
        return ""
    if asset_filename.endswith(".tex"):
        return f"\\input{{{asset_filename}}}\n"
    return f"\\includegraphics[width=0.85\\linewidth]{{{asset_filename}}}\n"


def build_mock_latex_document(request: CompletionRequest, *, refined: bool = False) -> str:
    citation_keys = extract_citation_keys(request.user_prompt)
    plot_ids = extract_plot_ids(request.user_prompt)
    plot_asset_paths = extract_plot_asset_paths(request.user_prompt)
    metric_tokens = extract_metric_tokens(request.user_prompt)
    cited = ",".join(citation_keys) if citation_keys else ""
    cite_clause = f"\\cite{{{cited}}}" if cited else ""
    plot_id = plot_ids[0] if plot_ids else "fig_framework_overview"
    asset_filename = plot_asset_paths[0] if plot_asset_paths else None
    metric_sentence = ""
    if metric_tokens:
        metric_sentence = " Reported grounded metrics include " + ", ".join(metric_tokens[:3]) + "."
    title_line = "Refined mock paper." if refined else "Mock paper output."
    figure_body = _figure_body(asset_filename)
    return f"""```latex
\\documentclass{{article}}
\\usepackage{{graphicx}}
\\begin{{document}}
{title_line}
\\section{{Introduction}}
PaperOrchestra frames manuscript generation as an artifact-driven workflow {cite_clause}.
\\section{{Related Work}}
Prior autonomous writing systems often remain tightly coupled to experimental loops {cite_clause}.
\\section{{Method}}
{MOCK_METHOD_BODY.format(plot_id=plot_id)}
\\begin{{figure}}
{figure_body}
\\caption{{Overview of the staged pipeline.}}
\\label{{{plot_id}}}
\\end{{figure}}
\\section{{Experiments}}
The evaluation emphasizes grounded writing and verified citations.{metric_sentence}
\\section{{Conclusion}}
The manuscript remains artifact-first and refinement-gated {cite_clause}.
\\end{{document}}
```"""
