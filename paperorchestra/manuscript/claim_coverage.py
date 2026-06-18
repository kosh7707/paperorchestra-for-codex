from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.claim_text import _section_visible_text, _visible_latex_text
from paperorchestra.manuscript.validation_types import ValidationIssue


def _coverage_term_variants(term: str) -> tuple[str, ...]:
    normalized = str(term).strip().lower()
    if not normalized:
        return ()
    irregular = {
        "boundary": ("boundary", "boundaries"),
        "boundaries": ("boundary", "boundaries"),
    }
    if normalized in irregular:
        return irregular[normalized]
    variants = {normalized}
    if normalized.endswith("y") and len(normalized) > 1:
        variants.add(normalized[:-1] + "ies")
    elif normalized.endswith("ies") and len(normalized) > 3:
        variants.add(normalized[:-3] + "y")
    elif normalized.endswith("s") and len(normalized) > 3:
        variants.add(normalized[:-1])
    else:
        variants.add(normalized + "s")
    return tuple(sorted(variants))


def _coverage_term_positions(section_text: str, term: str) -> tuple[int, ...]:
    lowered = section_text.lower()
    found: set[int] = set()
    for variant in _coverage_term_variants(term):
        if not variant:
            continue
        parts = [part for part in re.split(r"[\s-]+", variant) if part]
        if not parts:
            continue
        separator = r"(?:\s+|-)"
        pattern = re.compile(r"(?<![a-z0-9])" + separator.join(re.escape(part) for part in parts) + r"(?![a-z0-9])")
        found.update(match.start() for match in pattern.finditer(lowered))
    return tuple(sorted(found))


def _terms_nearby(section_text: str, terms: list[str], *, window: int = 360) -> bool:
    positioned_terms: list[tuple[int, int]] = []
    for term_index, term in enumerate(terms):
        positions = _coverage_term_positions(section_text, str(term))
        if not positions:
            return False
        positioned_terms.extend((position, term_index) for position in positions)
    positioned_terms.sort()
    required_count = len(terms)
    counts = [0] * required_count
    covered = 0
    left = 0
    for right, (right_position, right_term) in enumerate(positioned_terms):
        if counts[right_term] == 0:
            covered += 1
        counts[right_term] += 1
        while left <= right and right_position - positioned_terms[left][0] > window:
            _, left_term = positioned_terms[left]
            counts[left_term] -= 1
            if counts[left_term] == 0:
                covered -= 1
            left += 1
        if covered == required_count:
            return True
    return False


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
