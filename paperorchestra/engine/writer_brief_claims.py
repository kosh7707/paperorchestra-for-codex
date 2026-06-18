from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection, sanitize_author_facing_text
from paperorchestra.engine.prompt_context import _prompt_compact_text


def _claims_by_section_for_writer_brief(claim_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    claims_by_section: dict[str, list[dict[str, Any]]] = {}
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        projection = normalized_claim_projection(claim)
        section = str(projection.get("target_section") or "").strip() or "Unassigned"
        claims_by_section.setdefault(section, []).append(_claim_for_writer_brief(claim, projection))
    return claims_by_section


def _claim_for_writer_brief(claim: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    supporting_evidence = _safe_supporting_evidence(claim)
    return {
        "claim": _prompt_compact_text(str(projection.get("authorial_claim") or ""), head_chars=260, tail_chars=0),
        "type": projection.get("claim_type"),
        "grounding": _grounding_label(projection.get("grounding")),
        "required": bool(projection.get("required", True)),
        "risk": projection.get("risk"),
        "supporting_evidence": supporting_evidence,
        "supporting_excerpt": supporting_evidence[0]["excerpt"] if supporting_evidence else "",
        "coverage_terms": projection.get("coverage_groups") or [],
    }


def _grounding_label(grounding: Any) -> str | None:
    text = str(grounding or "").strip()
    return {
        "source_material": "technical_evidence",
        "experimental_log": "measurement_log",
        "human_boundary": "author_scope_constraints",
        "verified_citation": "verified_background_literature",
    }.get(text, text or None)


def _safe_supporting_evidence(claim: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = [_evidence_anchor_for_writer(anchor) for anchor in claim.get("evidence_anchors") or [] if isinstance(anchor, dict)]
    evidence = [item for item in evidence if item]
    legacy_excerpt = sanitize_author_facing_text(str(claim.get("excerpt") or ""), fallback="")
    if legacy_excerpt and not evidence:
        evidence.append({"excerpt": _prompt_compact_text(legacy_excerpt, head_chars=360, tail_chars=0)})
    return evidence


def _evidence_anchor_for_writer(anchor: dict[str, Any]) -> dict[str, Any]:
    excerpt = sanitize_author_facing_text(str(anchor.get("evidence_excerpt") or anchor.get("excerpt") or ""), fallback="")
    if not excerpt:
        return {}
    item: dict[str, Any] = {"excerpt": _prompt_compact_text(excerpt, head_chars=360, tail_chars=0)}
    line_start = anchor.get("line_start")
    line_end = anchor.get("line_end")
    if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0 and line_end >= line_start:
        item["location"] = f"lines {line_start}-{line_end}"
    return item
