from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.claim_coverage_terms import (
    _coverage_term_positions,
    _terms_nearby,
)
from paperorchestra.manuscript.claim_text import _section_visible_text, _visible_latex_text
from paperorchestra.manuscript.validation_types import ValidationIssue


def check_claim_map_coverage(latex: str, claim_map: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(claim_map, dict):
        return []
    issues: list[ValidationIssue] = []
    visible = _visible_latex_text(latex)
    if re.search(r"\bclaim_id\b|\bclaim-\d{3,}\b", visible, re.IGNORECASE):
        issues.append(
            ValidationIssue(
                code="prompt_meta_leakage",
                severity="error",
                message="Manuscript visibly leaks claim-map identifiers or claim_id metadata.",
            )
        )
    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict) or not claim.get("required"):
            continue
        claim_id = str(claim.get("id") or "required-claim")
        target = str(claim.get("target_section") or "")
        section_text = _section_visible_text(latex, target)
        if not section_text:
            issues.append(
                ValidationIssue(
                    code="required_claim_wrong_section",
                    severity="error",
                    message=f"Required claim {claim_id} is missing from target section {target}.",
                )
            )
            continue
        if not claim.get("evidence_anchors"):
            issues.append(
                ValidationIssue(
                    code="source_material_claim_omitted",
                    severity="error",
                    message=f"Required claim {claim_id} lacks evidence anchors and cannot be enforced safely.",
                )
            )
            continue
        groups = claim.get("coverage_groups") or []
        if not groups:
            flat_terms = claim.get("coverage_terms") or []
            groups = [[term] for term in flat_terms]
        satisfied = 0
        isolated_hits = 0
        for group in groups:
            terms = [str(term) for term in group if str(term).strip()]
            if not terms:
                continue
            if all(_coverage_term_positions(section_text, term) for term in terms):
                isolated_hits += 1
            if _terms_nearby(section_text, terms):
                satisfied += 1
        needed = max(1, min(len(groups), 2 if len(groups) <= 2 else 2))
        if satisfied < needed:
            code = "required_claim_keyword_stuffing" if isolated_hits >= needed else "required_claim_missing"
            issues.append(
                ValidationIssue(
                    code=code,
                    severity="error",
                    message=f"Required claim {claim_id} is not meaningfully covered in target section {target}.",
                )
            )
    return issues
