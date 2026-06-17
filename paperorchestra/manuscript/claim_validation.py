from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import control_prose_markers, normalized_coverage_groups
from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.manuscript.sections import _normalize_section_title, _section_bodies, _substantive_text
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


def _visible_latex_text(latex: str) -> str:
    lines = []
    for line in latex.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        lines.append(re.sub(r"(?<!\\)%.*", "", line))
    text = "\n".join(lines)
    text = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\bibliographystyle\{[^}]+\}|\\bibliography\{[^}]+\}", " ", text)
    return text


def _section_visible_text(latex: str, title: str) -> str:
    bodies = _section_bodies(_visible_latex_text(latex))
    return _substantive_text(bodies.get(_normalize_section_title(title), ""))


def _section_visible_latex(latex: str, title: str) -> str:
    bodies = _section_bodies(_visible_latex_text(latex))
    return bodies.get(_normalize_section_title(title), "")


def _claim_guard_text(text: str) -> str:
    stripped = re.sub(r"\\begin\{thebibliography\}.*", "", text, flags=re.DOTALL)
    stripped = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", stripped)
    stripped = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", stripped)
    stripped = stripped.replace("{", " ").replace("}", " ")
    stripped = re.sub(r"[%].*", " ", stripped)
    stripped = re.sub(r"[^A-Za-z0-9가-힣.,;:!?\"'“”‘’-]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _boundary_negates_phrase(prefix: str) -> bool:
    if re.search(
        r"\b(?:should\s+)?not\s+be\s+interpreted\s+as\s+"
        r"(?:(?:showing|meaning|implying)(?:[\w\s,;:-]{0,80})\bthat|evidence\s+that)\s*$",
        prefix,
    ):
        return True
    if re.search(r"\bno\s+one\s+should\s+(?:conclude|infer|read\s+this\s+as\s+claiming)\s+that\s*$", prefix):
        return True
    if re.search(r"\bnot\s+true\s+that\s*$", prefix):
        return True
    if re.search(r"\bno\s+evidence\s+(?:shows|suggests|demonstrates|establishes|implies)\s+that\s*$", prefix):
        return True
    if re.search(
        r"\b(?:the\s+)?(?:goal|aim|objective|purpose)\s+is\s+not\s+to\s+"
        r"(?:claim|assert|show|establish|demonstrate|imply|mean)(?:\s+that)?\s*$",
        prefix,
    ):
        return True
    if re.search(
        r"\bnor\s+do(?:es)?\s+(?:they|it|we|this|the\s+\w+)\s+guarantee\s+that\s+"
        r"(?:[\w\s-]{0,80}\s+)?(?:is|are|would\s+be|will\s+be)\s*$",
        prefix,
    ):
        return True
    direct_boundary_verb = r"(?:claim|assert|show|establish|demonstrate|imply|mean)"
    direct_boundary_modifier = r"(?:currently|directly|explicitly|actually|yet)"
    direct_boundary = re.search(
        r"\b(?:does|do)\s+not\s+"
        rf"(?:(?:{direct_boundary_modifier})\s+){{0,3}}"
        rf"{direct_boundary_verb}"
        rf"(?:\s*,\s*{direct_boundary_verb})*"
        rf"(?:\s*,?\s+(?:or|and)\s+{direct_boundary_verb})?"
        r"(?:\s+that)?\s*$",
        prefix,
    )
    if direct_boundary:
        leading = prefix[: direct_boundary.start()]
        current_sentence = re.split(r"[.;!?]", leading)[-1]
        attribution_subject = r"(?:the\s+)?[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,3}"
        reporting_verb = (
            r"(?:wrote|writes|said|say|says|state|states|stated|claim|claims|claimed|note|notes|noted|"
            r"argue|argues|argued|report|reports|reported|read|reads|comment|comments|remark|remarks)"
        )
        if (
            re.search(r"\b(?:according\s+to|per)\b", current_sentence)
            or re.search(r"\b(?:quoted?|quotation|excerpt)\s*[:,-]", current_sentence)
            or re.search(r"\bquote\b.*[:,-]", current_sentence)
            or re.search(attribution_subject + r"\s+" + reporting_verb + r"\s*[:,-]", current_sentence)
            or re.search(reporting_verb + r"\s*[:,-]\s*$", current_sentence)
        ):
            return False
        leading_segment = re.split(r"(?:[.;:!?]|,|\bbut\b|\byet\b(?!\s*$)|\bhowever\b)", leading)[-1].strip()
        safe_subject = (
            r"(?:"
            r"(?:the|this|our)(?:\s+current)?\s+(?:paper|manuscript|draft|system|workflow|evaluation|evidence|result|results)"
            r"|we"
            r"|it"
            r"|our\s+(?:paper|manuscript|draft|system|workflow|evaluation)"
            r")"
        )
        if re.fullmatch(
            r"(?:(?:overall|broadly|more\s+broadly)\s+)?"
            rf"{safe_subject}"
            r"(?:\s+(?:also|therefore|thus|accordingly))?"
            r"(?:\s+does\s+not\s+[a-z][a-z-]*(?:\s+[a-z][a-z-]*){0,8}\s+and)?",
            leading_segment,
        ):
            return True
    segment = re.split(r"(?:[.;:!?]|,|\bbut\b|\byet\b(?!\s*$)|\bhowever\b)", prefix)[-1]
    direct_negator = r"(?:never|no|without|non-?|not\s+(?:yet\s+|currently\s+|already\s+|actually\s+|really\s+|a\s+|an\s+|the\s+|that\s+)?)"
    return bool(re.search(r"\b" + direct_negator + r"$", segment))


def _contains_unnegated_phrase(text: str, phrase: str) -> bool:
    phrase_text = _substantive_text(phrase).lower()
    if not phrase_text:
        return False
    normalized = " " + _claim_guard_text(text).lower() + " "
    phrase_separator = r"(?:\s+|-)"
    pattern = re.compile(r"(?<!\w)" + phrase_separator.join(re.escape(part) for part in phrase_text.split()) + r"(?!\w)")
    for match in pattern.finditer(normalized):
        prefix = normalized[max(0, match.start() - 160) : match.start()]
        if _boundary_negates_phrase(prefix):
            continue
        return True
    return False


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


def _narrative_terms_from_item(item: Any) -> list[str]:
    if isinstance(item, dict):
        groups = normalized_coverage_groups(item)
        terms = [term for group in groups for term in group]
        if terms:
            return terms[:8]
        text = str(item.get("authorial_claim") or item.get("beat") or item.get("text") or "")
    else:
        text = str(item)
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", text)[:6]


def _narrative_item_covered(section_text: str, item: Any) -> bool:
    if isinstance(item, dict) and item.get("coverage_groups"):
        for group in normalized_coverage_groups(item):
            terms = [str(term) for term in group if str(term).strip()]
            if terms and _terms_nearby(section_text, terms):
                return True
        return False
    terms = _narrative_terms_from_item(item)
    return not terms or any(term.lower() in section_text.lower() for term in terms)


def check_narrative_section_roles(latex: str, narrative_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(narrative_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "")
        section_latex = _section_visible_latex(latex, title)
        section_text = _substantive_text(section_latex)
        role_items = role.get("coverage_requirements") or role.get("must_cover") or []
        for item in role_items:
            if not _narrative_item_covered(section_text, item):
                label = str(item.get("authorial_claim") if isinstance(item, dict) else item)[:120]
                issues.append(
                    ValidationIssue(
                        code="narrative_section_role_missing",
                        severity="error",
                        message=f"Section {title} does not cover required narrative role item: {label}",
                    )
                )
        for forbidden in role.get("must_not_claim") or []:
            if _contains_unnegated_phrase(section_latex, str(forbidden)):
                issues.append(
                    ValidationIssue(
                        code="narrative_forbidden_claim_present",
                        severity="error",
                        message=f"Section {title} contains forbidden narrative claim: {forbidden}",
                    )
                )
    for beat in narrative_plan.get("story_beats") or []:
        if not isinstance(beat, dict):
            continue
        target = str(beat.get("target_section") or "")
        section_text = _section_visible_text(latex, target)
        if not _narrative_item_covered(section_text, beat):
            issues.append(
                ValidationIssue(
                    code="narrative_story_beat_missing",
                    severity="error",
                    message=f"Story beat is missing from target section {target}: {str(beat.get('beat'))[:120]}",
                )
            )
    return issues
