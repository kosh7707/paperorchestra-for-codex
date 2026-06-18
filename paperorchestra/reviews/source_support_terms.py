from __future__ import annotations

import re

_STOP_TERMS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "uses",
    "use",
    "using",
    "for",
    "into",
    "also",
    "show",
    "shows",
    "describe",
    "describes",
    "discuss",
    "discusses",
    "guide",
    "guides",
    "guided",
    "systems",
    "system",
    "model",
    "models",
}


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _meaningful_terms(text: str) -> set[str]:
    return set(_meaningful_term_sequence(text))


def _meaningful_term_sequence(text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[a-z0-9]{3,}", text.lower()):
        term = _singularize_term(raw)
        if term not in _STOP_TERMS and term not in terms:
            terms.append(term)
    return terms


def _source_text_windows(text: str) -> list[str]:
    windows = [_collapse_ws(part) for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if _collapse_ws(part)]
    return windows or [_collapse_ws(text)]


def _singularize_term(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 3 and term.endswith("s"):
        return term[:-1]
    return term
