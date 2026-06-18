from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import control_prose_markers
from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.manuscript.claim_coverage import check_claim_map_coverage
from paperorchestra.manuscript.claim_text import _section_visible_latex, _visible_latex_text
from paperorchestra.manuscript.narrative_validation import check_narrative_section_roles
from paperorchestra.manuscript.validation_types import ValidationIssue


PROMPT_META_LEAKAGE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bcaption\s*intent\b",
        r"\brendering[_\s-]*brief\b",
        r"\bsource[_\s-]*fidelity(?:[_\s-]*notes)?\b",
        r"\binternal\s+visual\s+prompt\b",
        r"\bgeneration\s+objective\b|\binternal\s+generation\s+objective\b",
        r"\bfigure\s+prompt\b",
        r"\bprompt\s*/\s*meta\b|\bprompt\s+meta\b",
        r"\bsupplied\s+source\s+(?:boundary|material)\b",
        r"\bprovided\s+(?:method\s+)?material\b",
        r"\bsource[-\s]+grounded\b",
        r"\bsource\s+boundary\b",
        r"\bthe\s+draft\s+must\s+preserve\b",
        r"\bbenchmark\s+narrative\s+must\s+report\b",
        r"\bdraft\s+remains\s+bounded\b",
        r"\bdoes\s+not\s+add\s+an\s+external\s+claim\b",
        r"\bskipped_due_to_upstream_fail\b",
        r"\bdata_block\b|<\s*/?\s*DATA_BLOCK\b",
        r"\breviewer_feedback\b",
        r"\bscore_redaction\b|\bwriter_blind_to_reviewer_scores\b",
        r"\bas an ai\b",
        r"\blorem\s+ipsum\b|\bplaceholder\s+(?:figure|image|asset|text|caption)\b",
        r"\bTODO\b|\bTBD\b|\\todo\b",
        r"\bproof\s+omitted\b|\bomitted\s+proof\b",
        r"\binsert\s+(?:the\s+)?figure\b|\bfigure\s+to\s+be\s+inserted\b",
        r"\bcitation_map\.json\b|\bsection_writing\b",
        r"\bnarrative_plan(?:\.json)?\b|\bclaim_map(?:\.json)?\b|\bcitation_placement_plan(?:\.json)?\b",
        r"\bauthor[_\s-]*facing[_\s-]*writer[_\s-]*brief\b|\bwriter[_\s-]*brief(?:\.json)?\b",
        r"\bclaim_id\b|\bclaim-\d{3,}\b",
        r"\bartifact[-\s]+governed\s+drafting\b",
        r"\bpromotion[-\s]+time\s+validation\b",
        r"\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|review|source|material)\s+packet\b",
        r"\brevised\s+manuscript\b|\bsupplied\s+(?:library|material|technical\s+evidence)\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b|\bbenchmark\s+packet\b|\bempirical\s+packet\b|\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b|\bquality\s+gate\b|\breview\s+packet\b",
        # Catch leaked source-packet headings such as
        # ``\section{Claim Boundaries for the Draft}`` without banning ordinary
        # scholarly phrases like "assumptions, composition rationale, and claim
        # boundaries" in a limitations discussion.
        r"\\(?:sub)*section\*?\{\s*claim\s+boundaries(?:\s+for\s+(?:the\s+)?.+?\s+draft)?\s*\}",
        r"\bauthor\s+notes(?:\s+for\s+.+)?\b",
    ]
]


def check_prompt_meta_leakage(latex: str) -> list[ValidationIssue]:
    visible_text = _visible_latex_text(latex)
    if not any(pattern.search(visible_text) for pattern in PROMPT_META_LEAKAGE_PATTERNS) and not control_prose_markers(visible_text):
        return []
    return [
        ValidationIssue(
            code="prompt_meta_leakage",
            severity="error",
            message="Manuscript contains prompt/meta or internal generation text that must not appear in reviewable drafts.",
        )
    ]


def check_citation_placement(latex: str, citation_placement_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(citation_placement_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        claim_id = str(placement.get("claim_id") or "claim")
        target = str(placement.get("target_section") or "")
        section_text = _section_visible_latex(latex, target)
        keys = [str(key) for key in placement.get("citation_keys") or [] if str(key).strip()]
        missing = [key for key in keys if key not in extract_citation_keys(section_text)]
        if missing:
            issues.append(
                ValidationIssue(
                    code="citation_placement_missing",
                    severity="error",
                    message=f"Citation placement for {claim_id} is missing key(s) in {target}: {', '.join(missing)}",
                )
            )
    return issues
