from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.matching import normalize_title


def _safe_bibtex_key_part(text: str, *, fallback: str) -> str:
    normalized = "".join(ch for ch in normalize_title(text).title() if ch.isalnum())
    return normalized or fallback


def make_bibtex_key(paper: VerifiedPaper) -> str:
    author_source = paper.authors[0].split()[-1] if paper.authors else ""
    author = _safe_bibtex_key_part(author_source, fallback="Anon")
    year = str(paper.year or "nd")
    slug_words = normalize_title(paper.title).split()[:3]
    slug = "".join(word.capitalize() for word in slug_words if word.isalnum()) or "Paper"
    return f"{author.lower()}{year}{slug}"


def ensure_unique_bibtex_keys(registry: list[VerifiedPaper]) -> list[VerifiedPaper]:
    seen: set[str] = set()
    for paper in registry:
        base_key = paper.bibtex_key or make_bibtex_key(paper)
        candidate = base_key
        suffix = 2
        while candidate in seen:
            candidate = f"{base_key}{suffix}"
            suffix += 1
        paper.bibtex_key = candidate
        seen.add(candidate)
    return registry
