from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research import dates as _dates
from paperorchestra.research.bibtex import make_bibtex_key
from paperorchestra.research.literature_sources import search_semantic_scholar
from paperorchestra.research.matching import normalize_title, title_match_ratio
from paperorchestra.research.s2_api import SemanticScholarClient


def verify_candidate_title(
    title: str,
    *,
    cutoff_date: str | None = None,
    query_hint: str | None = None,
    min_ratio: float = 70.0,
    rate_limit_seconds: float = 1.0,
    client: SemanticScholarClient | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> VerifiedPaper | None:
    candidates = search_semantic_scholar(title, limit=5, client=client)
    best: dict[str, Any] | None = None
    best_ratio = -1.0
    for candidate in candidates:
        ratio = title_match_ratio(title, candidate.get("title", ""))
        year = candidate.get("year")
        if year and query_hint and any(char.isdigit() for char in query_hint):
            if str(year) in query_hint:
                ratio += 5.0
        if ratio > best_ratio:
            best_ratio = ratio
            best = candidate
    if rate_limit_seconds > 0:
        (sleep_fn or time.sleep)(rate_limit_seconds)
    if not best or best_ratio < min_ratio:
        return None
    abstract = best.get("abstract") or ""
    if not abstract.strip():
        return None
    paper = VerifiedPaper(
        paper_id=best["paperId"],
        title=best["title"],
        year=best.get("year"),
        publication_date=best.get("publicationDate"),
        venue=best.get("venue"),
        abstract=abstract,
        authors=[author.get("name", "") for author in best.get("authors", []) if author.get("name")],
        citation_count=best.get("citationCount"),
        external_ids=best.get("externalIds") or {},
        url=best.get("url"),
        matched_query=query_hint or title,
        title_match_ratio=round(min(best_ratio, 100.0), 2),
        is_after_cutoff=not _dates.year_month_passes_cutoff(best.get("year"), cutoff_date, best.get("publicationDate")),
    )
    paper.bibtex_key = make_bibtex_key(paper)
    return paper


def serialize_registry(path: str | Path, registry: list[VerifiedPaper]) -> None:
    Path(path).write_text(json.dumps([asdict(item) for item in registry], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def mock_verified_paper(
    title: str,
    *,
    abstract_hint: str,
    cutoff_date: str | None = None,
    origin: str | None = None,
    query_hint: str | None = None,
) -> VerifiedPaper:
    normalized = normalize_title(title) or "paper"
    synthetic_id = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    paper = VerifiedPaper(
        paper_id=f"mock-{synthetic_id}",
        title=title.strip(),
        year=_dates.parse_cutoff(cutoff_date).year if cutoff_date else None,
        publication_date=None,
        venue="Mock Venue",
        abstract=abstract_hint.strip() or f"Mock abstract for {title.strip()}",
        authors=["Mock Author"],
        citation_count=None,
        url=None,
        matched_query=query_hint or title,
        title_match_ratio=100.0,
        is_after_cutoff=False,
        origin=origin,
    )
    paper.bibtex_key = make_bibtex_key(paper)
    return paper
