from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.claim_validation import (
    PROMPT_META_LEAKAGE_PATTERNS,
    _boundary_negates_phrase,
    _claim_guard_text,
    _contains_unnegated_phrase,
    _coverage_term_positions,
    _coverage_term_variants,
    _narrative_item_covered,
    _narrative_terms_from_item,
    _section_visible_latex,
    _section_visible_text,
    _terms_nearby,
    _visible_latex_text,
    check_citation_placement,
    check_claim_map_coverage,
    check_narrative_section_roles,
    check_prompt_meta_leakage,
)
from paperorchestra.manuscript.validation_types import ValidationIssue
from paperorchestra.manuscript.citations import (
    CITE_COMMAND_RE,
    allowed_citation_keys,
    canonical_citation_key,
    canonical_citation_keys,
    canonical_citation_map,
    canonicalize_citation_keys,
    citation_entry_for_key,
    extract_citation_keys,
    noncanonical_citation_aliases,
)
from paperorchestra.manuscript.figure_validation import (
    CAPTION_RE,
    FIGURE_ENV_RE,
    INCLUDE_GRAPHICS_RE,
    LABEL_RE,
    REF_RE,
    FigurePlacementWarning,
    build_figure_placement_review,
)
from paperorchestra.manuscript.sections import (
    SECTION_RE,
    _normalize_section_title,
    _section_bodies,
    _substantive_text,
)

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


def check_unknown_citations(latex: str, citation_map: dict[str, Any]) -> list[ValidationIssue]:
    cited_keys = extract_citation_keys(latex)
    unknown_keys = sorted(key for key in cited_keys if key not in allowed_citation_keys(citation_map))
    if not unknown_keys:
        return []
    return [
        ValidationIssue(
            code="unknown_citation_keys",
            severity="error",
            message=f"Unknown citation keys referenced in LaTeX: {', '.join(unknown_keys)}",
        )
    ]


def _citation_coverage_requirement(population: int) -> int:
    if population <= 0:
        return 0
    if population <= 10:
        return population
    if population <= 25:
        return max(1, int(round(population * 0.85)))
    if population <= 50:
        return max(1, int(round(population * 0.8)))
    return max(1, int(round(population * 0.7)))


def check_citation_coverage(latex: str, citation_map: dict[str, Any]) -> list[ValidationIssue]:
    if not citation_map:
        return []
    cited_keys = extract_citation_keys(latex)
    allowed = allowed_citation_keys(citation_map)
    cited_canonical = {canonical_citation_key(key, citation_map) if key in citation_map else key for key in cited_keys if key in allowed}
    population = len(canonical_citation_keys(citation_map))
    required_citation_count = _citation_coverage_requirement(population)
    if len(cited_canonical) >= required_citation_count:
        return []
    return [
        ValidationIssue(
            code="citation_coverage_insufficient",
            severity="error",
            message=(
                f"Insufficient citation coverage: cited {len(cited_canonical)} verified papers, "
                f"need at least {required_citation_count}."
            ),
        )
    ]


def check_figure_file_coverage(latex: str, figures_dir: str | None) -> list[ValidationIssue]:
    if not figures_dir:
        return []
    figure_dir_path = Path(figures_dir)
    required_figure_names = [
        path.name
        for path in figure_dir_path.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
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
            message=(
                "Manuscript contains decimal/percent values not grounded in the experimental log: "
                + ", ".join(unsupported_numeric_tokens)
            ),
        )
    ]


def check_comparative_claims(latex: str, experimental_log_text: str | None) -> list[ValidationIssue]:
    if not experimental_log_text:
        return []
    lowered_log = experimental_log_text.lower()
    lowered_latex = latex.lower()
    unsupported_claim_patterns = [
        pattern for pattern in COMPARATIVE_CLAIM_PATTERNS if pattern in lowered_latex and pattern not in lowered_log
    ]
    if not unsupported_claim_patterns:
        return []
    return [
        ValidationIssue(
            code="unsupported_comparative_claim",
            severity="warning",
            message=(
                "Manuscript contains comparative claims not evidenced in the experimental log: "
                + ", ".join(sorted(set(unsupported_claim_patterns)))
            ),
        )
    ]


































def validate_manuscript(
    latex: str,
    *,
    citation_map: dict[str, Any],
    figures_dir: str | None,
    plot_manifest: dict[str, Any] | None = None,
    plot_assets_index: dict[str, Any] | None = None,
    experimental_log_text: str | None = None,
    expected_section_titles: list[str] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    claim_map: dict[str, Any] | None = None,
    citation_placement_plan: dict[str, Any] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(check_prompt_meta_leakage(latex))
    issues.extend(check_unknown_citations(latex, citation_map))
    aliases = noncanonical_citation_aliases(latex, citation_map)
    if aliases:
        detail = ", ".join(f"{src}->{dst}" for src, dst in sorted(aliases.items()))
        issues.append(
            ValidationIssue(
                code="noncanonical_citation_aliases",
                severity="error",
                message=f"Noncanonical citation aliases must be rewritten before validation/compile: {detail}.",
            )
        )
    issues.extend(check_citation_coverage(latex, citation_map))
    issues.extend(check_figure_file_coverage(latex, figures_dir))
    issues.extend(check_plot_plan_coverage(latex, plot_manifest))
    issues.extend(check_generated_plot_asset_usage(latex, plot_assets_index))
    issues.extend(check_expected_section_substance(latex, expected_section_titles))
    issues.extend(check_numeric_grounding(latex, experimental_log_text))
    issues.extend(check_comparative_claims(latex, experimental_log_text))
    issues.extend(check_claim_map_coverage(latex, claim_map))
    issues.extend(check_citation_placement(latex, citation_placement_plan))
    issues.extend(check_narrative_section_roles(latex, narrative_plan))
    return issues
