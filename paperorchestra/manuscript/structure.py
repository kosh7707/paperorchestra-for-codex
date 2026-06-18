from __future__ import annotations

from paperorchestra.manuscript.structure_insertion import _insert_block_into_section, _paragraph_insertion_index, _preferred_section_name
from paperorchestra.manuscript.structure_patterns import LABEL_RE, SECTION_COMMAND_RE, SUBSECTION_COMMAND_RE
from paperorchestra.manuscript.structure_ranges import _normalized_section_range_map, _section_range_map
from paperorchestra.manuscript.structure_titles import _canonical_generated_section_title

__all__ = [
    "LABEL_RE",
    "SECTION_COMMAND_RE",
    "SUBSECTION_COMMAND_RE",
    "_canonical_generated_section_title",
    "_insert_block_into_section",
    "_normalized_section_range_map",
    "_paragraph_insertion_index",
    "_preferred_section_name",
    "_section_range_map",
]
