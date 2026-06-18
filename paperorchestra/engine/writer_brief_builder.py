from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.engine.prompt_context import _prompt_compact_text
from paperorchestra.engine.writer_brief_claims import _claims_by_section_for_writer_brief
from paperorchestra.engine.writer_brief_guidance import _citation_guidance_for_writer_brief
from paperorchestra.engine.writer_brief_sections import _section_roles_for_writer_brief
from paperorchestra.engine.writer_brief_validation import _validate_author_facing_writer_brief


def _writer_brief_from_planning(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project planning artifacts into an author-facing prose brief."""
    claims_by_section = _claims_by_section_for_writer_brief(claim_map)
    brief = {
        "thesis": _writer_brief_thesis(narrative_plan),
        "contribution_boundary": _contribution_boundary(narrative_plan),
        "section_roles": _section_roles_for_writer_brief(narrative_plan, claims_by_section),
        "citation_guidance": _citation_guidance_for_writer_brief(citation_placement_plan),
        "authoring_rules": [
            "Write only scholarly paper prose.",
            "Use external citations for background, standards, baselines, and contrast; keep core method, proof, and result claims tied to technical evidence.",
            "State limitations as normal scholarly scope conditions rather than process disclaimers.",
        ],
    }
    _validate_author_facing_writer_brief(brief)
    return brief


def _writer_brief_thesis(narrative_plan: dict[str, Any]) -> str:
    return _prompt_compact_text(
        sanitize_author_facing_text(
            str(narrative_plan.get("thesis") or ""),
            fallback="Build a coherent scholarly draft that preserves the paper's stated claims, scope, and citation positioning.",
        ),
        head_chars=500,
        tail_chars=0,
    )


def _contribution_boundary(narrative_plan: dict[str, Any]) -> list[str]:
    return [
        sanitize_author_facing_text(
            str(item),
            fallback="State evidence limits as ordinary scholarly assumptions, scope, and limitations.",
        )
        for item in (narrative_plan.get("contribution_boundary") or [])
        if str(item).strip()
    ]
