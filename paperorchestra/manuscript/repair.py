from __future__ import annotations

from paperorchestra.manuscript.repair_claims import (
    _citation_map_for_selected_sections,
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _required_claim_scope_note,
)
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
