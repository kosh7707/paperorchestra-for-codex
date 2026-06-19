from __future__ import annotations

import re

from paperorchestra.core.boundary_control import control_prose_markers


def sanitize_author_facing_text(text: str | None, *, fallback: str = "") -> str:
    value = str(text or "").strip()
    if not value:
        return fallback
    replacements: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bhuman[-\s]*provided\b", re.IGNORECASE), "the paper's"),
        (
            re.compile(
                r"\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|review|source|material)\s+packet\b",
                re.IGNORECASE,
            ),
            "stated evidence",
        ),
        (
            re.compile(
                r"\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b",
                re.IGNORECASE,
            ),
            "stated evidence",
        ),
        (re.compile(r"\bfollowing\s+the\s+packet\b", re.IGNORECASE), "Based on the stated evidence"),
        (re.compile(r"\b(?:as\s+)?specified\s+in\s+the\s+packet\b", re.IGNORECASE), "According to the stated evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?benchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?empirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?review\s+packet\b", re.IGNORECASE), "reviewed evidence"),
        (re.compile(r"\b(?:method|construction|proof|benchmark|empirical|review|source|material)\s+packet\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsupplied\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsupplied technical evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided technical evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided)\s+evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided)\s+theorem\s+statements?\b", re.IGNORECASE), "theorem statements"),
        (re.compile(r"\bsupplied source material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided source material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsource material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided|available)\s+logs?\b", re.IGNORECASE), "measurement log"),
        (re.compile(r"\bavailable\s+(?:materials?|sources?|files?)\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided)\s+(?:files?|analyses|analysis)\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsupplied materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided materials?\b", re.IGNORECASE), "stated evidence"),
        (
            re.compile(
                r"\bno\s+reviewable\s+figure\s+files\s+were\s+available\b|\breviewable\s+figure\s+files\s+were\s+not\s+available\b",
                re.IGNORECASE,
            ),
            "figures are outside this draft's current scope",
        ),
        (re.compile(r"\bavailable\s+(?:source\s+)?(?:materials?|logs?|files?|artifacts?)\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsource boundaries\b", re.IGNORECASE), "scope boundaries"),
        (re.compile(r"\bsource boundary\b", re.IGNORECASE), "scope boundary"),
        (re.compile(r"\bclaim boundaries\b", re.IGNORECASE), "technical boundary and scope"),
        (re.compile(r"\bmanuscript\s+plan\b", re.IGNORECASE), "paper outline"),
        (re.compile(r"\b(?:already\s+)?supplied\s+with\s+the\s+stated\s+evidence\b", re.IGNORECASE), "stated in the evidence"),
    )
    rewritten = value
    for pattern, replacement in replacements:
        rewritten = pattern.sub(replacement, rewritten)
    if not control_prose_markers(rewritten):
        return rewritten
    return fallback or "State evidence limits as ordinary scholarly assumptions, scope, and limitations."


__all__ = ["sanitize_author_facing_text"]
