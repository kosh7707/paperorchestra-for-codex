from __future__ import annotations

from typing import Any

from paperorchestra.domains import detect_domain_for_text
from paperorchestra.manuscript.narrative_claim_appenders import (
    _append_benchmark_claim,
    _append_limitation_claim,
    _append_method_claim,
    _append_positioning_claim,
    _append_proof_claim,
)
from paperorchestra.manuscript.narrative_sections import NarrativeSectionTargets


def build_claims(
    *,
    state: Any,
    planning_text: str,
    author_source_text: str,
    template_planning_text: str,
    log_planning_text: str,
    citation_map: dict[str, Any],
    targets: NarrativeSectionTargets,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    idx = 1
    domain = detect_domain_for_text(planning_text)
    idx = _append_method_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        planning_text=planning_text,
        author_source_text=author_source_text,
        template_planning_text=template_planning_text,
        target_section=targets.method,
    )
    idx = _append_proof_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        planning_text=planning_text,
        template_planning_text=template_planning_text,
        target_section=targets.proof,
    )
    idx = _append_benchmark_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        log_planning_text=log_planning_text,
        target_section=targets.results,
    )
    idx = _append_limitation_claim(
        claims,
        idx=idx,
        state=state,
        planning_text=planning_text,
        target_section=targets.discussion,
    )
    _append_positioning_claim(
        claims,
        idx=idx,
        state=state,
        citation_map=citation_map,
        target_section=targets.positioning,
    )
    return claims
