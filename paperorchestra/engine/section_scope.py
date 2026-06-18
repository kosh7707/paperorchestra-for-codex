from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.boundary import is_material_packet_control_section_title, is_material_packet_section_title
from paperorchestra.manuscript.structure import SECTION_COMMAND_RE, _canonical_generated_section_title, _section_range_map
from paperorchestra.manuscript.validator import ValidationIssue


def _preserve_existing_sections(generated_latex: str, source_latex: str, *, section_names: list[str]) -> str:
    merged = generated_latex
    source_ranges = _section_range_map(source_latex)
    for section_name in section_names:
        normalized = section_name.strip().lower()
        source_range = source_ranges.get(normalized)
        if source_range is None:
            continue
        target_ranges = _section_range_map(merged)
        target_range = target_ranges.get(normalized)
        if target_range is None:
            continue
        source_block = source_latex[source_range[0] : source_range[1]]
        merged = merged[: target_range[0]] + source_block + merged[target_range[1] :]
    return merged


def _preserve_all_except_sections(generated_latex: str, source_latex: str, *, rewritten_section_names: list[str]) -> str:
    protected_names = []
    rewritten = {name.strip().lower() for name in rewritten_section_names if name and name.strip()}
    for section_name in _section_range_map(source_latex):
        if section_name not in rewritten:
            protected_names.append(section_name)
    return _preserve_existing_sections(generated_latex, source_latex, section_names=protected_names)


def _normalize_section_selection(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,;]+", value)
    selected: list[str] = []
    for item in raw_items:
        text = str(item).strip()
        if text:
            selected.append(text)
    return selected


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
        raise ContractError(
            "Unknown section name(s) for --only-sections: " + ", ".join(unknown)
        )
    return resolved


def _filtered_outline_for_sections(outline: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    selected = {item.strip().lower() for item in selected_sections}
    filtered = dict(outline)
    section_plan = outline.get("section_plan", []) if isinstance(outline, dict) else []
    filtered["section_plan"] = [
        item
        for item in section_plan
        if isinstance(item, dict) and str(item.get("section_title") or "").strip().lower() in selected
    ]
    return filtered


def _selected_section_template(source_latex: str, selected_sections: list[str]) -> str:
    ranges = _section_range_map(source_latex)
    matches = list(SECTION_COMMAND_RE.finditer(source_latex))
    preamble_end = matches[0].start() if matches else source_latex.find("\\begin{document}")
    if preamble_end == -1:
        preamble_end = 0
    preamble = source_latex[:preamble_end]
    blocks: list[str] = []
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower())
        if section_range is None:
            continue
        blocks.append(source_latex[section_range[0] : section_range[1]])
    end_document = "\\end{document}\n" if "\\end{document}" in source_latex else ""
    return preamble + "".join(blocks) + end_document


def _expected_section_titles_from_outline(outline: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    saw_material_packet_control_section = False
    ignored = {
        "abstract",
        "appendix",
        "cross-cutting citation coverage checklist",
    }
    for item in outline.get("section_plan", []):
        if not isinstance(item, dict):
            continue
        title = item.get("section_title")
        if isinstance(title, str) and title.strip():
            normalized = _canonical_generated_section_title(title)
            if is_material_packet_control_section_title(title):
                saw_material_packet_control_section = True
            if (
                normalized in ignored
                or normalized.startswith("appendix")
                or is_material_packet_section_title(title)
                or "checklist" in normalized
            ):
                continue
            titles.append(normalized if normalized in {"method", "experiments", "discussion"} else title.strip())
    if saw_material_packet_control_section and not any(title.strip().lower() == "discussion" for title in titles):
        titles.append("Discussion")
    return titles

