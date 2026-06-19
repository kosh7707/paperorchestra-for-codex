from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.structure import _canonical_generated_section_title

_RELATED_WORK_TITLES = {"related work", "background and related work"}


def can_bridge_retry_citation_coverage(blocking_issues: list[Any], selected_sections: list[str]) -> bool:
    if not blocking_issues or {issue.code for issue in blocking_issues} - {"citation_coverage_insufficient"}:
        return False
    if not selected_sections:
        return True
    selected_titles = {_canonical_generated_section_title(section) for section in selected_sections}
    return bool(selected_titles & _RELATED_WORK_TITLES)
