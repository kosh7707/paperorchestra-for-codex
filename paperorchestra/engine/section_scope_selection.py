from __future__ import annotations

import re

from paperorchestra.core.errors import ContractError
from paperorchestra.manuscript.structure import _section_range_map
from paperorchestra.manuscript.validation_types import ValidationIssue


def _normalize_section_selection(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else re.split(r"[\n,;]+", value)
    selected: list[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text:
            selected.append(text)
    return selected


def _resolve_selected_sections(source_latex: str, selected_sections: list[str]) -> list[str]:
    source_ranges = _section_range_map(source_latex)
    resolved: list[str] = []
    unknown: list[str] = []
    for item in selected_sections:
        normalized = item.strip().lower()
        if normalized in source_ranges:
            resolved.append(item.strip())
        else:
            unknown.append(item.strip())
    if unknown:
        raise ContractError("Unknown section name(s) for --only-sections: " + ", ".join(unknown))
    return resolved


def _filter_section_scoped_issues(issues: list[ValidationIssue], *, selected_sections: list[str]) -> list[ValidationIssue]:
    if not selected_sections:
        return issues
    normalized = {item.strip().lower() for item in selected_sections}
    result: list[ValidationIssue] = []
    for issue in issues:
        if issue.code == "citation_coverage_insufficient":
            continue
        if issue.code == "numeric_grounding_mismatch" and normalized.isdisjoint({"implementation and results", "experiments"}):
            continue
        result.append(issue)
    return result
