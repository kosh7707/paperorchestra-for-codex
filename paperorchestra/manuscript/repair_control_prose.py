from __future__ import annotations

import re

LATEX_CITATION_COMMAND_RE = re.compile(
    r"\\(?P<name>(?!nocite\b)[A-Za-z]*cite[A-Za-z]*)(?P<star>\*)?(?P<opts>(?:\s*\[[^\]]*\]){0,2})\s*\{(?P<keys>[^}]+)\}",
    re.IGNORECASE,
)


def _rewrite_legacy_scope_notes(latex: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        claim = match.group(1).strip()
        if not claim:
            return match.group(0)
        if not claim.endswith("."):
            claim += "."
        return f"{claim} The statement is scoped to the evidence and assumptions presented in this paper."

    return re.sub(
        r"Source-grounded scope note:\s*(.*?)\s*This sentence is derived from the supplied material and preserves the section's source boundary without adding a new external claim\.",
        _replace,
        latex,
        flags=re.DOTALL,
    )


_MANUSCRIPT_CONTROL_PROSE_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?m)^[ \t]*%[ \t]*PaperOrchestra writes this\.[ \t]*\n?"), ""),
    (re.compile(r"\bfollowing\s+the\s+packet\b", re.IGNORECASE), "Based on the stated evidence"),
    (re.compile(r"\b(?:as\s+)?specified\s+in\s+the\s+packet\b", re.IGNORECASE), "According to the stated evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?benchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?empirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
    (re.compile(r"\b(?:(?:supplied|provided)\s+)?review\s+packet\b", re.IGNORECASE), "reviewed evidence"),
    (
        re.compile(
            r"\b(?:supplied|provided)\s+packet\b|\b(?:(?:supplied|provided)\s+)?(?:method|construction|proof|benchmark|empirical|review|source|material)\s+packet\b",
            re.IGNORECASE,
        ),
        "stated evidence",
    ),
    (
        re.compile(r"\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b", re.IGNORECASE),
        "stated evidence",
    ),
    (re.compile(r"\bsource[-\s]+grounded\b", re.IGNORECASE), "evidence-bounded"),
    (re.compile(r"\bsupplied\s+source\s+(?:boundary|material)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+source\s+(?:boundary|material)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsupplied\s+source\b", re.IGNORECASE), "stated specification"),
    (re.compile(r"\bprovided\s+source\b", re.IGNORECASE), "stated specification"),
    (re.compile(r"\bsupplied\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsupplied\s+technical\s+evidence\b", re.IGNORECASE), "stated technical evidence"),
    (re.compile(r"\bprovided\s+technical\s+evidence\b", re.IGNORECASE), "stated technical evidence"),
    (re.compile(r"\b(?:supplied|provided)\s+evidence\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\b(?:supplied|provided)\s+theorem\s+statements?\b", re.IGNORECASE), "theorem statements"),
    (re.compile(r"\b(?:supplied|provided|available)\s+logs?\b", re.IGNORECASE), "measurement log"),
    (re.compile(r"\bavailable\s+(?:materials?|sources?|files?)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\b(?:supplied|provided)\s+(?:files?|analyses|analysis)\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsupplied\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bprovided\s+materials?\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bsource\s+boundary\b", re.IGNORECASE), "scope boundary"),
    (re.compile(r"\bsource\s+material\b", re.IGNORECASE), "stated evidence"),
    (re.compile(r"\bthe\s+draft\s+must\s+preserve\b", re.IGNORECASE), "the analysis preserves"),
    (re.compile(r"\bbenchmark\s+narrative\s+must\s+report\b", re.IGNORECASE), "the benchmark analysis reports"),
    (re.compile(r"\bdraft\s+remains\s+bounded\b", re.IGNORECASE), "claims remain bounded"),
    (re.compile(r"\bdoes\s+not\s+add\s+an\s+external\s+claim\b", re.IGNORECASE), "does not broaden the paper's claims"),
    (re.compile(r"\bmanuscript\s+plan\b", re.IGNORECASE), "paper outline"),
    (re.compile(r"\bbenchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
    (re.compile(r"\bempirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
    (re.compile(r"\breview\s+packet\b", re.IGNORECASE), "reviewed evidence"),
    (re.compile(r"\bquality\s+gate\b", re.IGNORECASE), "quality criterion"),
    (
        re.compile(r"\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b", re.IGNORECASE),
        "figures are not part of this evaluation",
    ),
    (re.compile(r"\b(?:already\s+)?supplied\s+with\s+the\s+stated\s+evidence\b", re.IGNORECASE), "stated in the evidence"),
)


def _normalize_portable_citation_commands(latex: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        star = match.group("star") or ""
        opts = match.group("opts") or ""
        keys = match.group("keys")
        if name == "cite" and not star and opts.count("[") <= 1:
            return match.group(0)
        return f"\\cite{{{keys}}}"

    return LATEX_CITATION_COMMAND_RE.sub(_replace, latex)


def _sanitize_manuscript_control_prose(latex: str) -> str:
    rendered = _rewrite_legacy_scope_notes(latex)
    rendered = re.sub(r"\\[Cc]ref\b", r"\\ref", rendered)
    rendered = re.sub(r"\\(Table|Figure|Section|Theorem|Lemma|Corollary|Appendix)(?=\s*~?\s*\\ref\b)", r"\1", rendered)
    rendered = _normalize_portable_citation_commands(rendered)
    for pattern, replacement in _MANUSCRIPT_CONTROL_PROSE_REWRITES:
        rendered = pattern.sub(replacement, rendered)
    return rendered
