from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.manuscript import structure as _structure
from paperorchestra.manuscript.repair_text import (
    _repair_inline_math_surplus_closing_brace,
    _sanitize_manuscript_control_prose,
)


def _required_claim_scope_note(claim: dict[str, Any]) -> str:
    projection = normalized_claim_projection(claim)
    note = str(projection.get("scope_note") or "").strip()
    if not note:
        return ""
    if not note.endswith("."):
        note += "."
    return note + "\n\n"


def _ensure_required_claim_scope_notes(latex: str, claim_map: dict[str, Any] | None) -> str:
    if not isinstance(claim_map, dict):
        return _repair_inline_math_surplus_closing_brace(_sanitize_manuscript_control_prose(latex))
    rendered = _sanitize_manuscript_control_prose(latex)
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict) or not claim.get("required", True):
            continue
        note = _required_claim_scope_note(claim)
        if not note:
            continue
        target = _structure._canonical_generated_section_title(str(claim.get("target_section") or ""))
        ranges = _structure._normalized_section_range_map(rendered)
        if target not in ranges:
            continue
        start, end = ranges[target]
        section_block = rendered[start:end]
        if note.strip() in section_block:
            continue
        section_title_end = rendered.find("}", start, end)
        insert_at = _structure._paragraph_insertion_index(rendered, section_title_end + 1 if section_title_end != -1 else start, end)
        rendered = rendered[:insert_at] + "\n" + note + rendered[insert_at:]
    return _repair_inline_math_surplus_closing_brace(rendered)
