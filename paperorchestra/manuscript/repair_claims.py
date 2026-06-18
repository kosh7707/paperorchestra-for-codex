from __future__ import annotations

from paperorchestra.manuscript.repair_citation_selection import _citation_map_for_selected_sections
from paperorchestra.manuscript.repair_claim_scope import _ensure_required_claim_scope_notes, _required_claim_scope_note
from paperorchestra.manuscript.repair_discussion_boundaries import _ensure_discussion_section_for_claim_boundaries

__all__ = [
    "_citation_map_for_selected_sections",
    "_ensure_discussion_section_for_claim_boundaries",
    "_ensure_required_claim_scope_notes",
    "_required_claim_scope_note",
]
