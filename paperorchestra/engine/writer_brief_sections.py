from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.engine.prompt_context import _prompt_compact_text


def _section_roles_for_writer_brief(
    narrative_plan: dict[str, Any],
    claims_by_section: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    section_roles = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "").strip()
        required_claims = claims_by_section.get(title, [])
        section_roles.append(
            {
                "section": title,
                "role": _section_role_text(role),
                "must_cover": _section_must_cover(role, required_claims),
                "must_not_claim": role.get("must_not_claim") or [],
                "required_claims": required_claims,
            }
        )
    return section_roles


def _section_role_text(role: dict[str, Any]) -> str:
    return _prompt_compact_text(
        sanitize_author_facing_text(
            str(role.get("role") or ""),
            fallback="Develop this section from stated evidence, assumptions, and assigned citations.",
        ),
        head_chars=260,
        tail_chars=0,
    )


def _section_must_cover(role: dict[str, Any], required_claims: list[dict[str, Any]]) -> list[str]:
    if required_claims:
        return [claim["claim"] for claim in required_claims if claim.get("claim")]
    return [str(item) for item in role.get("must_cover") or [] if str(item).strip()]
