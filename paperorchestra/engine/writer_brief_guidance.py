from __future__ import annotations

from typing import Any

from paperorchestra.engine.prompt_context import _prompt_compact_text


def _citation_guidance_for_writer_brief(citation_placement_plan: dict[str, Any]) -> list[dict[str, Any]]:
    guidance: list[dict[str, Any]] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        guidance.append(
            {
                "section": placement.get("target_section"),
                "citation_keys": placement.get("citation_keys") or [],
                "purpose": _prompt_compact_text(
                    str(placement.get("purpose") or placement.get("rationale") or ""),
                    head_chars=220,
                    tail_chars=0,
                ),
            }
        )
    return guidance
