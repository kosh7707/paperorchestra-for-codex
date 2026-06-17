from __future__ import annotations

import re
from difflib import SequenceMatcher

SEARCH_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "before",
    "beyond",
    "by",
    "do",
    "does",
    "establish",
    "find",
    "focusing",
    "for",
    "from",
    "help",
    "how",
    "in",
    "introduce",
    "introducing",
    "justify",
    "long",
    "made",
    "need",
    "new",
    "not",
    "of",
    "on",
    "or",
    "papers",
    "paper",
    "post",
    "prioritize",
    "published",
    "reviews",
    "search",
    "seeking",
    "systems",
    "that",
    "the",
    "their",
    "these",
    "to",
    "use",
    "why",
    "with",
    "writing",
}


def normalize_title(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def title_match_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() * 100.0


def _query_keywords(text: str) -> list[str]:
    tokens = normalize_title(text).split()
    return [
        token
        for token in tokens
        if (token == "ai" or len(token) >= 3) and token not in SEARCH_QUERY_STOPWORDS
    ]


def _result_overlap_score(query: str, title: str, abstract: str = "") -> int:
    query_terms = set(_query_keywords(query))
    if not query_terms:
        return 0
    result_terms = set(_query_keywords(f"{title} {abstract}"))
    return len(query_terms & result_terms)


def grounded_result_is_relevant(query: str, title: str, abstract: str = "") -> bool:
    query_terms = _query_keywords(query)
    if not query_terms:
        return True
    if len(query_terms) <= 2:
        return True
    if title_match_ratio(query, title) >= 55.0:
        return True
    overlap = _result_overlap_score(query, title, abstract)
    if len(query_terms) <= 4:
        return overlap >= 1
    if len(query_terms) <= 8:
        return overlap >= 2
    return overlap >= 3


def _is_exact_seed_query(query: str) -> bool:
    words = [re.sub(r"[^A-Za-z0-9-]+", "", token) for token in query.split()]
    words = [word for word in words if word]
    if not words:
        return False
    has_exact_seed_markers = any(char.isdigit() for char in query) or "-" in query or "(" in query or ")" in query
    if has_exact_seed_markers:
        return len(words) <= 12
    if len(words) > 8:
        return False
    if has_exact_seed_markers:
        return True
    titled = sum(1 for word in words if word[:1].isupper())
    return len(words) <= 4 and titled >= max(1, len(words) - 1)


def _seed_query_matches_result(query: str, title: str) -> bool:
    if title_match_ratio(query, title) >= 70.0:
        return True
    normalized_query = normalize_title(query)
    normalized_title = normalize_title(title)
    return normalized_query == normalized_title
