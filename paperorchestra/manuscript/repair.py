from __future__ import annotations

from typing import Any

from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.citations import canonical_citation_key, canonical_citation_map, extract_citation_keys
from paperorchestra.manuscript.repair_claim_scope import _ensure_required_claim_scope_notes, _required_claim_scope_note
from paperorchestra.manuscript.repair_discussion_boundaries import _ensure_discussion_section_for_claim_boundaries
from paperorchestra.manuscript.repair_text import (
    INLINE_MATH_RE,
    LATEX_CITATION_COMMAND_RE,
    _MANUSCRIPT_CONTROL_PROSE_REWRITES,
    _ensure_text_safe_math_macros,
    _move_macro_definitions_to_preamble,
    _normalize_portable_citation_commands,
    _remove_material_packet_sections,
    _repair_inline_math_surplus_closing_brace,
    _rewrite_legacy_scope_notes,
    _sanitize_manuscript_control_prose,
    _trim_one_trailing_unescaped_brace,
    _unescaped_brace_delta,
)


def _citation_map_for_selected_sections(source_latex: str, citation_map: dict[str, Any], selected_sections: list[str]) -> dict[str, Any]:
    if not citation_map:
        return {}
    ranges = _structure._section_range_map(source_latex)
    selected_keys: set[str] = set()
    for section_name in selected_sections:
        section_range = ranges.get(section_name.strip().lower())
        if section_range is None:
            continue
        block = source_latex[section_range[0] : section_range[1]]
        selected_keys.update(extract_citation_keys(block))
    compact = canonical_citation_map(citation_map)
    if not selected_keys:
        return compact
    canonical_selected = {canonical_citation_key(key, citation_map) for key in selected_keys if key in citation_map}
    subset = {key: value for key, value in compact.items() if key in canonical_selected}
    return subset or compact
