from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.claim_validation import (
    check_citation_placement as _check_citation_placement,
    check_claim_map_coverage as _check_claim_map_coverage,
    check_narrative_section_roles as _check_narrative_section_roles,
    check_prompt_meta_leakage as _check_prompt_meta_leakage,
)
from paperorchestra.manuscript.citations import noncanonical_citation_aliases
from paperorchestra.manuscript.validation_types import ValidationIssue
from paperorchestra.manuscript.validator_citations import (
    _citation_coverage_requirement,
    check_citation_coverage,
    check_unknown_citations,
)
from paperorchestra.manuscript.validator_content import (
    COMPARATIVE_CLAIM_PATTERNS,
    _sanitize_layout_numbers,
    check_comparative_claims,
    check_expected_section_substance,
    check_figure_file_coverage,
    check_generated_plot_asset_usage,
    check_numeric_grounding,
    check_plot_plan_coverage,
    extract_decimal_like_tokens,
)


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
    issues.extend(_check_prompt_meta_leakage(latex))
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
    issues.extend(_check_claim_map_coverage(latex, claim_map))
    issues.extend(_check_citation_placement(latex, citation_placement_plan))
    issues.extend(_check_narrative_section_roles(latex, narrative_plan))
    return issues
