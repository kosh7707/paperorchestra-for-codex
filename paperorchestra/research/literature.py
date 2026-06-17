from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.s2_api import SemanticScholarClient, SemanticScholarError, get_default_semantic_scholar_client
from paperorchestra.research.bibtex import make_bibtex_key
from paperorchestra.research.dates import parse_cutoff, parse_publication_date, year_month_passes_cutoff
from paperorchestra.research.prior_work_seed import (
    _coerce_year,
    _entry_external_ids,
    _extract_bibtex_field,
    _normalize_doi,
    _normalize_seed_entry,
    _parse_bibtex_seed,
    _parse_json_seed,
    _parse_markdown_seed,
    _split_authors,
    load_prior_work_seed,
    prior_work_entries_to_verified_papers,
)
from paperorchestra.research.matching import (
    _is_exact_seed_query,
    _seed_query_matches_result,
    grounded_result_is_relevant,
    normalize_title,
    title_match_ratio,
)

OPENALEX_WORKS_SEARCH = "https://api.openalex.org/works"
def _cache_dir(service: str) -> Path:
    path = Path(".paper-orchestra") / "cache" / service
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(service: str, query: str, limit: int) -> Path:
    key = hashlib.sha256(f"{query}::{limit}".encode("utf-8")).hexdigest()
    return _cache_dir(service) / f"{key}.json"


def _http_get_json(url: str, *, service: str = "semantic_scholar") -> dict[str, Any]:
    headers = {
        "User-Agent": "paperorchestra-reconstruction/0.1",
        "Accept": "application/json",
    }
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key and service == "semantic_scholar":
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        service_label = "Semantic Scholar" if service == "semantic_scholar" else service
        if exc.code == 429:
            raise SemanticScholarError(
                f"{service_label} rate-limited the request (HTTP 429). Set SEMANTIC_SCHOLAR_API_KEY, reduce request volume, or retry later."
            ) from exc
        raise SemanticScholarError(f"{service_label} request failed with HTTP {exc.code}.") from exc


def search_semantic_scholar(
    query: str,
    *,
    limit: int = 5,
    client: SemanticScholarClient | None = None,
) -> list[dict[str, Any]]:
    cache_path = _cache_path("semantic_scholar", query, limit)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("data", [])
    active_client = client if client is not None else get_default_semantic_scholar_client()
    data = active_client.search_papers(query, limit=limit)
    if not getattr(active_client, "last_response_was_fallback", False):
        cache_path.write_text(json.dumps({"data": data}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data



def search_openalex(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    cache_path = _cache_path("openalex", query, limit)
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("results", [])
    params = {
        "search": query,
        "per-page": limit,
        "select": "id,display_name,publication_year,publication_date,primary_location,abstract_inverted_index,doi",
    }
    url = OPENALEX_WORKS_SEARCH + "?" + urllib.parse.urlencode(params)
    payload = _http_get_json(url, service="openalex")
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload.get("results", [])


def _openalex_abstract(result: dict[str, Any]) -> str:
    inverted = result.get("abstract_inverted_index") or {}
    if not isinstance(inverted, dict) or not inverted:
        return ""
    words: list[tuple[int, str]] = []
    for token, positions in inverted.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int):
                words.append((pos, token))
    return " ".join(word for _, word in sorted(words))


def _title_from_openalex(result: dict[str, Any]) -> str:
    return str(result.get("display_name") or "").strip()


def _year_from_openalex(result: dict[str, Any]) -> int | None:
    year = result.get("publication_year")
    return int(year) if isinstance(year, int) else None


def build_search_grounded_candidates(
    queries: list[str],
    *,
    macro_query_count: int,
    cutoff_date: str | None = None,
    per_source_limit: int = 3,
    mode: str = "live",
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    payload: dict[str, list[dict[str, Any]]] = {"macro_candidates": [], "micro_candidates": []}
    seen_titles: set[str] = set()
    candidate_index: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    def _append_candidate(*, bucket: str, title: str, why_relevant: str, origin_query: str, discovery_source: str, year: int | None, publication_date: str | None = None) -> None:
        normalized = normalize_title(title)
        if not normalized or normalized in seen_titles:
            existing = candidate_index.get(normalized)
            if existing is not None:
                sources = existing.setdefault("discovery_sources", [])
                if discovery_source not in sources:
                    sources.append(discovery_source)
            if not normalized:
                return
            return
        if not year_month_passes_cutoff(year, cutoff_date, publication_date):
            return
        seen_titles.add(normalized)
        candidate = {
            "title_guess": title,
            "why_relevant": why_relevant,
            "origin_query": origin_query,
            "role_guess": "macro" if bucket == "macro_candidates" else "micro",
            "discovery_source": discovery_source,
            "discovery_sources": [discovery_source],
        }
        payload[bucket].append(candidate)
        candidate_index[normalized] = candidate

    for idx, query in enumerate(queries):
        bucket = "macro_candidates" if idx < macro_query_count else "micro_candidates"
        exact_seed_query = _is_exact_seed_query(query)
        matched_any = False
        if mode == "mock":
            for source in ("semantic_scholar", "openalex"):
                title = query.strip()
                _append_candidate(
                    bucket=bucket,
                    title=title,
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
            _append_candidate(
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
            _append_candidate(
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
            _append_candidate(
                bucket=bucket,
                title=query.strip(),
                why_relevant=f"Preserved exact grounded seed from the session materials: {query}",
                origin_query=query,
                discovery_source="session_seed",
                year=2024,
                publication_date="2024-01-01",
            )
            notes.append(f"Exact grounded seed preserved without matching live result: {query}")

    return payload, notes

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
        is_after_cutoff=not year_month_passes_cutoff(best.get("year"), cutoff_date, best.get("publicationDate")),
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
        year=parse_cutoff(cutoff_date).year if cutoff_date else None,
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
