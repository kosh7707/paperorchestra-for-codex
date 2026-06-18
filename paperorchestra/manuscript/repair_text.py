from __future__ import annotations

from paperorchestra.core.boundary import is_material_packet_section_title
from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.repair_control_prose import (
    LATEX_CITATION_COMMAND_RE,
    _MANUSCRIPT_CONTROL_PROSE_REWRITES,
    _normalize_portable_citation_commands,
    _rewrite_legacy_scope_notes,
    _sanitize_manuscript_control_prose,
)
from paperorchestra.manuscript.repair_math_macros import (
    INLINE_MATH_RE,
    _ensure_text_safe_math_macros,
    _move_macro_definitions_to_preamble,
    _repair_inline_math_surplus_closing_brace,
    _trim_one_trailing_unescaped_brace,
    _unescaped_brace_delta,
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

__all__ = [
    "INLINE_MATH_RE",
    "LATEX_CITATION_COMMAND_RE",
    "_MANUSCRIPT_CONTROL_PROSE_REWRITES",
    "_ensure_text_safe_math_macros",
    "_move_macro_definitions_to_preamble",
    "_normalize_portable_citation_commands",
    "_remove_material_packet_sections",
    "_repair_inline_math_surplus_closing_brace",
    "_rewrite_legacy_scope_notes",
    "_sanitize_manuscript_control_prose",
    "_trim_one_trailing_unescaped_brace",
    "_unescaped_brace_delta",
]
