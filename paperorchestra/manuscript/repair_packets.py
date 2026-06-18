from __future__ import annotations

from paperorchestra.core.boundary import is_material_packet_section_title
from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.repair_math_macros import (
    _ensure_text_safe_math_macros,
    _move_macro_definitions_to_preamble,
)


def _remove_material_packet_sections(latex: str) -> str:
    ranges = _structure._section_range_map(latex)
    rendered = latex
    for title, (start, end) in sorted(ranges.items(), key=lambda item: item[1][0], reverse=True):
        if not is_material_packet_section_title(title):
            continue
        block = rendered[start:end]
        rendered = rendered[:start].rstrip() + "\n\n" + rendered[end:].lstrip()
        if title == "00 core macros":
            rendered = _move_macro_definitions_to_preamble(rendered, block)
    return _ensure_text_safe_math_macros(rendered)
