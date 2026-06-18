from __future__ import annotations

from typing import Any

from paperorchestra.research.literature_sources import (
    _openalex_abstract,
    _title_from_openalex,
    _year_from_openalex,
    search_openalex,
    search_semantic_scholar,
)
from paperorchestra.research.literature_candidate_accumulator import CandidateAccumulator
from paperorchestra.research.matching import (
    _is_exact_seed_query,
    _seed_query_matches_result,
    grounded_result_is_relevant,
)


def build_search_grounded_candidates(
    queries: list[str],
    *,
    macro_query_count: int,
    cutoff_date: str | None = None,
    per_source_limit: int = 3,
    mode: str = "live",
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    accumulator = CandidateAccumulator(cutoff_date=cutoff_date)
    notes: list[str] = []

    for idx, query in enumerate(queries):
        bucket = "macro_candidates" if idx < macro_query_count else "micro_candidates"
        exact_seed_query = _is_exact_seed_query(query)
        matched_any = False
        if mode == "mock":
            for source in ("semantic_scholar", "openalex"):
                accumulator.append_candidate(
                    bucket=bucket,
                    title=query.strip(),
                    why_relevant=f"Recovered via {source} mock grounded search for query: {query}",
                    origin_query=query,
                    discovery_source=source,
                    year=2024,
                    publication_date="2024-01-01",
                )
                matched_any = True
            notes.append(f"Mock grounded query completed: {query}")
            continue
        try:
            scholar_results = search_semantic_scholar(query, limit=per_source_limit)
            notes.append(f"Semantic Scholar grounded query completed: {query}")
        except Exception as exc:  # pragma: no cover - defensive live-path guard
            scholar_results = []
            notes.append(f"Semantic Scholar grounded query failed for '{query}': {exc}")
        for result in scholar_results:
            title = str(result.get("title") or "").strip()
            if not title:
                continue
            abstract = str(result.get("abstract") or "").strip()
            if exact_seed_query and not _seed_query_matches_result(query, title):
                continue
            if not grounded_result_is_relevant(query, title, abstract):
                continue
            accumulator.append_candidate(
                bucket=bucket,
                title=title,
                why_relevant=abstract or f"Recovered via Semantic Scholar grounded search for query: {query}",
                origin_query=query,
                discovery_source="semantic_scholar",
                year=result.get("year") if isinstance(result.get("year"), int) else None,
                publication_date=result.get("publicationDate"),
            )
            matched_any = True

        try:
            openalex_results = search_openalex(query, limit=per_source_limit)
            notes.append(f"OpenAlex grounded query completed: {query}")
        except Exception as exc:  # pragma: no cover - defensive live-path guard
            openalex_results = []
            notes.append(f"OpenAlex grounded query failed for '{query}': {exc}")
        for result in openalex_results:
            title = _title_from_openalex(result)
            if not title:
                continue
            abstract = _openalex_abstract(result)
            if exact_seed_query and not _seed_query_matches_result(query, title):
                continue
            if not grounded_result_is_relevant(query, title, abstract):
                continue
            accumulator.append_candidate(
                bucket=bucket,
                title=title,
                why_relevant=abstract or f"Recovered via OpenAlex grounded search for query: {query}",
                origin_query=query,
                discovery_source="openalex",
                year=_year_from_openalex(result),
                publication_date=result.get("publication_date"),
            )
            matched_any = True

        if exact_seed_query and not matched_any:
            accumulator.append_candidate(
                bucket=bucket,
                title=query.strip(),
                why_relevant=f"Preserved exact grounded seed from the session materials: {query}",
                origin_query=query,
                discovery_source="session_seed",
                year=2024,
                publication_date="2024-01-01",
            )
            notes.append(f"Exact grounded seed preserved without matching live result: {query}")

    return accumulator.payload, notes
