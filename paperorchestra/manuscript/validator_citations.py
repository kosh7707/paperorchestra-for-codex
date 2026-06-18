from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.citations import (
    allowed_citation_keys,
    canonical_citation_key,
    canonical_citation_keys,
    extract_citation_keys,
)
from paperorchestra.manuscript.validation_types import ValidationIssue


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
