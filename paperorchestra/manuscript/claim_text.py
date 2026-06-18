from __future__ import annotations

import re

from paperorchestra.manuscript.sections import _normalize_section_title, _section_bodies, _substantive_text


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
