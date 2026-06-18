from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.sections import _normalize_section_title, _section_bodies, _substantive_text
from paperorchestra.manuscript.validation_types import ValidationIssue

COMPARATIVE_CLAIM_PATTERNS = [
    "state-of-the-art",
    "sota",
    "outperform",
    "outperforms",
    "outperformed",
    "beats",
    "better than",
    "superior to",
]


def extract_decimal_like_tokens(text: str) -> set[str]:
    tokens = set()
    for match in re.finditer(r"\b\d+\.\d+(?:%|x|×)?\b|\b\d+\.\d+\\times\b|\b\d+%", text):
        token = match.group(0)
        token = token.removesuffix(r"\times").removesuffix("×").removesuffix("x")
        tokens.add(token)
    return tokens


def _sanitize_layout_numbers(latex: str) -> str:
    sanitized = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "<bibliography>", latex, flags=re.S)
    sanitized = re.sub(r"width\s*=\s*\d+\.\d+\\[A-Za-z]+", "width=<layout>", sanitized)
    sanitized = re.sub(r"scale\s*=\s*\d+\.\d+", "scale=<layout>", sanitized)
    sanitized = re.sub(r"p\{\d+\.\d+\\[A-Za-z]+\}", "p{<layout>}", sanitized)
    sanitized = re.sub(r"\\begin\{minipage\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\begin{minipage}{<layout>}", sanitized)
    sanitized = re.sub(r"\\renewcommand\{\\arraystretch\}\{\d+\.\d+\}", r"\\renewcommand{\\arraystretch}{<layout>}", sanitized)
    sanitized = re.sub(r"\\setlength\{[^}]+\}\{\d+\.\d+\\[A-Za-z]+\}", r"\\setlength{<layout>}{<layout>}", sanitized)
    return sanitized


def check_figure_file_coverage(latex: str, figures_dir: str | None) -> list[ValidationIssue]:
    if not figures_dir:
        return []
    figure_dir_path = Path(figures_dir)
    required_figure_names = [path.name for path in figure_dir_path.iterdir() if path.is_file() and not path.name.startswith(".")]
    missing_figures = [name for name in required_figure_names if name not in latex]
    if not missing_figures:
        return []
    return [
        ValidationIssue(
            code="figure_file_not_referenced",
            severity="warning",
            message=f"Provided figures not referenced in LaTeX: {', '.join(missing_figures)}",
        )
    ]


def check_plot_plan_coverage(latex: str, plot_manifest: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_manifest:
        return []
    lowered_latex = latex.lower()
    missing_plot_coverage = []
    for figure in plot_manifest.get("figures", []):
        figure_id = figure.get("figure_id", "")
        title = figure.get("title", "")
        caption = figure.get("caption", "")
        if figure_id and figure_id.lower() in lowered_latex:
            continue
        if title and title.lower() in lowered_latex:
            continue
        if caption and caption.lower() in lowered_latex:
            continue
        if figure_id:
            missing_plot_coverage.append(figure_id)
    if not missing_plot_coverage:
        return []
    return [
        ValidationIssue(
            code="plot_plan_not_reflected",
            severity="error",
            message="Plot-plan figures are not represented in the manuscript: " + ", ".join(sorted(missing_plot_coverage)),
        )
    ]


def check_generated_plot_asset_usage(latex: str, plot_assets_index: dict[str, Any] | None) -> list[ValidationIssue]:
    if not plot_assets_index:
        return []
    assets = plot_assets_index.get("assets", []) if isinstance(plot_assets_index, dict) else []
    missing_assets = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_kind") == "generated_placeholder" or asset.get("review_status") == "human_final_artwork_required":
            continue
        filename = asset.get("filename")
        snippet_path = asset.get("latex_snippet_path")
        latex_path = asset.get("latex_path")
        if isinstance(snippet_path, str) and snippet_path and snippet_path in latex:
            continue
        if isinstance(latex_path, str) and latex_path and latex_path in latex:
            continue
        if isinstance(filename, str) and filename and filename in latex:
            continue
        if isinstance(filename, str) and filename:
            missing_assets.append(filename)
    if not missing_assets:
        return []
    return [
        ValidationIssue(
            code="generated_plot_asset_not_used",
            severity="warning",
            message="Generated plot assets are not referenced in the manuscript: " + ", ".join(sorted(missing_assets)),
        )
    ]


def check_expected_section_substance(
    latex: str,
    expected_section_titles: list[str] | None,
    *,
    min_body_chars: int = 120,
) -> list[ValidationIssue]:
    if not expected_section_titles:
        return []
    bodies = _section_bodies(latex)
    missing: list[str] = []
    shallow: list[str] = []
    ignored = {"abstract", "appendix", "references", "bibliography"}
    for raw_title in expected_section_titles:
        title = _normalize_section_title(raw_title)
        if not title or title in ignored or title.startswith("appendix"):
            continue
        body = bodies.get(title)
        if body is None:
            missing.append(raw_title)
            continue
        if len(_substantive_text(body)) < min_body_chars:
            shallow.append(raw_title)
    issues = []
    if missing:
        issues.append(
            ValidationIssue(
                code="expected_section_missing",
                severity="error",
                message="Expected sections are missing from the manuscript: " + ", ".join(missing),
            )
        )
    if shallow:
        issues.append(
            ValidationIssue(
                code="expected_section_too_shallow",
                severity="error",
                message=f"Expected sections have too little substantive body text (<{min_body_chars} chars): " + ", ".join(shallow),
            )
        )
    return issues


def check_numeric_grounding(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    allowed_numeric_tokens = extract_decimal_like_tokens(experimental_log_text)
    manuscript_numeric_tokens = extract_decimal_like_tokens(_sanitize_layout_numbers(latex))
    unsupported_numeric_tokens = sorted(manuscript_numeric_tokens - allowed_numeric_tokens)
    if not unsupported_numeric_tokens:
        return []
    return [
        ValidationIssue(
            code="numeric_grounding_mismatch",
            severity="error",
            message="Manuscript contains decimal/percent values not grounded in the experimental log: " + ", ".join(unsupported_numeric_tokens),
        )
    ]


def check_comparative_claims(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    lowered_log = experimental_log_text.lower()
    lowered_latex = latex.lower()
    unsupported_claim_patterns = [pattern for pattern in COMPARATIVE_CLAIM_PATTERNS if pattern in lowered_latex and pattern not in lowered_log]
    if not unsupported_claim_patterns:
        return []
    return [
        ValidationIssue(
            code="unsupported_comparative_claim",
            severity="warning",
            message="Manuscript contains comparative claims not evidenced in the experimental log: " + ", ".join(sorted(set(unsupported_claim_patterns))),
        )
    ]
