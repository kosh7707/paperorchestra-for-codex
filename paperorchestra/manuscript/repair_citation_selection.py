from __future__ import annotations

from typing import Any

from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.citations import canonical_citation_key, canonical_citation_map, extract_citation_keys


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
