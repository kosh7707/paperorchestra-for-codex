from __future__ import annotations

from paperorchestra.core.boundary_claim_projection import normalized_claim_projection, projection_for_claims
from paperorchestra.core.boundary_claim_text import (
    authorial_claim_text,
    generic_authorial_claim,
    scope_note_text,
)
from paperorchestra.core.boundary_claim_values import _as_strings, normalized_coverage_groups
from paperorchestra.core.boundary_patterns import CONTROL_PROSE_PATTERNS, control_prose_markers, is_machine_control_prose
from paperorchestra.core.boundary_payload import _walk_strings, assert_author_facing_payload, author_facing_payload_markers
from paperorchestra.core.boundary_sanitize import sanitize_author_facing_text
from paperorchestra.core.boundary_sections import (
    is_material_packet_control_section_title,
    is_material_packet_section_title,
    normalized_title,
)

__all__ = [
    "CONTROL_PROSE_PATTERNS",
    "_as_strings",
    "_walk_strings",
    "assert_author_facing_payload",
    "author_facing_payload_markers",
    "authorial_claim_text",
    "control_prose_markers",
    "generic_authorial_claim",
    "is_machine_control_prose",
    "is_material_packet_control_section_title",
    "is_material_packet_section_title",
    "normalized_claim_projection",
    "normalized_coverage_groups",
    "normalized_title",
    "projection_for_claims",
    "sanitize_author_facing_text",
    "scope_note_text",
]
