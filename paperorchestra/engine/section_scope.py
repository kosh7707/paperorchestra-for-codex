from __future__ import annotations

from paperorchestra.engine.section_scope_outline import _expected_section_titles_from_outline, _filtered_outline_for_sections
from paperorchestra.engine.section_scope_preservation import (
    _preserve_all_except_sections,
    _preserve_existing_sections,
    _selected_section_template,
)
from paperorchestra.engine.section_scope_selection import (
    _filter_section_scoped_issues,
    _normalize_section_selection,
    _resolve_selected_sections,
)

__all__ = [
    "_expected_section_titles_from_outline",
    "_filter_section_scoped_issues",
    "_filtered_outline_for_sections",
    "_normalize_section_selection",
    "_preserve_all_except_sections",
    "_preserve_existing_sections",
    "_resolve_selected_sections",
    "_selected_section_template",
]
