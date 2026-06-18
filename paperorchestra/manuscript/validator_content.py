from __future__ import annotations

from paperorchestra.manuscript.validator_figures import (
    check_figure_file_coverage,
    check_generated_plot_asset_usage,
    check_plot_plan_coverage,
)
from paperorchestra.manuscript.validator_numeric import (
    COMPARATIVE_CLAIM_PATTERNS,
    check_comparative_claims,
    check_numeric_grounding,
    extract_decimal_like_tokens,
    sanitize_layout_numbers,
)
from paperorchestra.manuscript.validator_sections import check_expected_section_substance

_sanitize_layout_numbers = sanitize_layout_numbers

__all__ = [
    "COMPARATIVE_CLAIM_PATTERNS",
    "_sanitize_layout_numbers",
    "check_comparative_claims",
    "check_expected_section_substance",
    "check_figure_file_coverage",
    "check_generated_plot_asset_usage",
    "check_numeric_grounding",
    "check_plot_plan_coverage",
    "extract_decimal_like_tokens",
]
