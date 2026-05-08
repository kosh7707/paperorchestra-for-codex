from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError

from .models import VerifiedPaper
from .s2_api import SemanticScholarClient, SemanticScholarError, get_default_semantic_scholar_client

OPENALEX_WORKS_SEARCH = "https://api.openalex.org/works"
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


def title_match_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() * 100.0


def normalize_title(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


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


def parse_cutoff(cutoff_date: str | None) -> dt.date | None:
    if not cutoff_date:
        return None
    return dt.date.fromisoformat(cutoff_date)


def parse_publication_date(publication_date: str | None) -> dt.date | None:
    if not publication_date:
        return None
    return dt.date.fromisoformat(publication_date[:10])


def year_month_passes_cutoff(year: int | None, cutoff_date: str | None, publication_date: str | None = None) -> bool:
    cutoff = parse_cutoff(cutoff_date)
    if cutoff is None or year is None:
        return True
    parsed_publication_date = parse_publication_date(publication_date)
    if parsed_publication_date is not None:
        return parsed_publication_date < cutoff
    if year < cutoff.year:
        return True
    if year > cutoff.year:
        return False
    return cutoff.month == 12 and cutoff.day == 31


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


def _coerce_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            return int(match.group(0))
    return None


def _split_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                result.append(item["name"].strip())
            elif isinstance(item, str):
                result.append(item.strip())
        return [item for item in result if item]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"\s+and\s+|;\s*|,\s*(?=[A-Z][A-Za-z]+(?:\s|$))", value) if item.strip()]
    return []


def _entry_external_ids(entry: dict[str, Any]) -> dict[str, str]:
    external = entry.get("externalIds") or entry.get("external_ids") or {}
    result = {str(k): str(v) for k, v in external.items()} if isinstance(external, dict) else {}
    doi = entry.get("doi") or entry.get("DOI")
    normalized_doi = _normalize_doi(doi) if isinstance(doi, str) else None
    if normalized_doi:
        result["DOI"] = normalized_doi
    arxiv = entry.get("arxiv") or entry.get("ArXiv")
    if isinstance(arxiv, str) and arxiv.strip():
        result["ArXiv"] = arxiv.strip()
    return result


def _normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\b(10\.\d{4,9}/[^\s,;{}]+)", value)
    if not match:
        return None
    return match.group(1).rstrip(").,;")


def _normalize_seed_entry(entry: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    title = str(entry.get("title") or entry.get("paper_title") or "").strip()
    if not title:
        return None
    source = str(entry.get("source") or entry.get("provenance") or default_source).strip() or default_source
    return {
        "title": title,
        "authors": _split_authors(entry.get("authors") or entry.get("author")),
        "bibtex_key": str(entry.get("bibtex_key") or "").strip() or None,
        "year": _coerce_year(entry.get("year") or entry.get("publication_year") or entry.get("date")),
        "publication_date": entry.get("publicationDate") or entry.get("publication_date"),
        "venue": str(entry.get("venue") or entry.get("journal") or entry.get("booktitle") or "").strip() or None,
        "abstract": str(entry.get("abstract") or entry.get("summary") or entry.get("notes") or f"Curated prior-work seed imported from {source}.").strip(),
        "citation_count": entry.get("citationCount") if isinstance(entry.get("citationCount"), int) else None,
        "external_ids": _entry_external_ids(entry),
        "url": str(entry.get("url") or entry.get("link") or "").strip() or None,
        "source": source,
        "provenance_notes": [
            str(item).strip()
            for item in (
                entry.get("provenance_notes")
                if isinstance(entry.get("provenance_notes"), list)
                else [entry.get("provenance_note") or entry.get("note") or ""]
            )
            if str(item).strip()
        ],
    }


def _parse_json_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = (
            payload.get("references")
            or payload.get("papers")
            or payload.get("prior_work")
            or payload.get("entries")
            or []
        )
    else:
        raw_entries = []
    result: list[dict[str, Any]] = []
    for item in raw_entries:
        if isinstance(item, dict):
            normalized = _normalize_seed_entry(item, default_source=default_source)
            if normalized:
                result.append(normalized)
    return result


def _extract_bibtex_field(body: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*", body, re.IGNORECASE)
    if not match:
        return None
    idx = match.end()
    while idx < len(body) and body[idx].isspace():
        idx += 1
    if idx >= len(body):
        return None
    opener = body[idx]
    if opener == "{":
        depth = 0
        start = idx + 1
        idx += 1
        while idx < len(body):
            ch = body[idx]
            if ch == "{" and (idx == 0 or body[idx - 1] != "\\"):
                depth += 1
            elif ch == "}" and (idx == 0 or body[idx - 1] != "\\"):
                if depth == 0:
                    return re.sub(r"\s+", " ", body[start:idx]).strip()
                depth -= 1
            idx += 1
        return None
    if opener == '"':
        start = idx + 1
        idx += 1
        while idx < len(body):
            if body[idx] == '"' and body[idx - 1] != "\\":
                return re.sub(r"\s+", " ", body[start:idx]).strip()
            idx += 1
    bare_match = re.match(r"([^,\n]+)", body[idx:])
    return bare_match.group(1).strip() if bare_match else None


def _parse_bibtex_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"@\w+\s*\{\s*([^,]+)\s*,(.*?)(?=\n@\w+\s*\{|\Z)", text, re.DOTALL):
        key = match.group(1).strip()
        body = match.group(2)
        fields: dict[str, str] = {"source": default_source, "provenance_note": f"Imported from BibTeX key {key}.", "bibtex_key": key}
        for field in ["title", "author", "year", "journal", "booktitle", "venue", "url", "doi", "abstract"]:
            value = _extract_bibtex_field(body, field)
            if value:
                fields[field] = value
        normalized = _normalize_seed_entry(fields, default_source=default_source)
        if normalized:
            entries.append(normalized)
    return entries

def _parse_markdown_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        item = stripped.lstrip("-* ").strip()
        if not item:
            continue
        url = None
        link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", item)
        if link_match:
            title = link_match.group(1).strip()
            url = link_match.group(2).strip()
        else:
            title = re.split(r"\s+[—–-]\s+|\s+\|\s+", item, maxsplit=1)[0].strip()
        title = re.sub(r"^\d+\.\s*", "", title).strip(" .")
        if len(title) < 4:
            continue
        year = _coerce_year(item)
        entries.append(
            {
                "title": title,
                "authors": [],
                "year": year,
                "publication_date": f"{year}-01-01" if year else None,
                "venue": None,
                "abstract": f"Curated prior-work seed imported from markdown line: {item}",
                "citation_count": None,
                "external_ids": _entry_external_ids({"doi": _normalize_doi(item)}),
                "url": url,
                "source": default_source,
                "provenance_notes": [item],
            }
        )
    return entries


def load_prior_work_seed(path: str | Path, *, source: str = "manual_seed") -> list[dict[str, Any]]:
    seed_path = Path(path)
    text = seed_path.read_text(encoding="utf-8")
    suffix = seed_path.suffix.lower()
    if suffix == ".json":
        return _parse_json_seed(text, default_source=source)
    if suffix in {".bib", ".bibtex"} or text.lstrip().startswith("@"):
        return _parse_bibtex_seed(text, default_source=source)
    return _parse_markdown_seed(text, default_source=source)


def prior_work_entries_to_verified_papers(
    entries: list[dict[str, Any]],
    *,
    cutoff_date: str | None = None,
) -> list[VerifiedPaper]:
    registry: list[VerifiedPaper] = []
    seen: dict[str, VerifiedPaper] = {}
    for index, entry in enumerate(entries, start=1):
        title = str(entry.get("title") or "").strip()
        normalized = normalize_title(title)
        if not normalized:
            continue
        year = _coerce_year(entry.get("year"))
        publication_date = entry.get("publication_date") if isinstance(entry.get("publication_date"), str) else None
        if not year_month_passes_cutoff(year, cutoff_date, publication_date):
            continue
        source = str(entry.get("source") or "manual_seed")
        key_hint = str(entry.get("bibtex_key") or "").strip() or None
        existing = seen.get(normalized)
        if existing is not None:
            if key_hint and key_hint != existing.bibtex_key and key_hint not in existing.alias_bibtex_keys:
                existing.alias_bibtex_keys.append(key_hint)
            continue
        paper = VerifiedPaper(
            paper_id=f"{source}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}",
            title=title,
            year=year,
            publication_date=publication_date,
            venue=entry.get("venue") if isinstance(entry.get("venue"), str) else None,
            abstract=str(entry.get("abstract") or f"Curated prior-work seed imported from {source}."),
            authors=_split_authors(entry.get("authors")),
            citation_count=entry.get("citation_count") if isinstance(entry.get("citation_count"), int) else None,
            external_ids=entry.get("external_ids") if isinstance(entry.get("external_ids"), dict) else {},
            url=entry.get("url") if isinstance(entry.get("url"), str) else None,
            origin=source,
            matched_query=title,
            title_match_ratio=100.0,
            is_after_cutoff=False,
        )
        paper.bibtex_key = str(key_hint).strip() if isinstance(key_hint, str) and str(key_hint).strip() else make_bibtex_key(paper)
        registry.append(paper)
        seen[normalized] = paper
    registry = ensure_unique_bibtex_keys(registry)
    used_keys = {paper.bibtex_key for paper in registry if paper.bibtex_key}
    for paper in registry:
        deduped_aliases: list[str] = []
        for alias in paper.alias_bibtex_keys:
            if not alias or alias == paper.bibtex_key or alias in used_keys:
                continue
            used_keys.add(alias)
            deduped_aliases.append(alias)
        paper.alias_bibtex_keys = deduped_aliases
    return registry




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


_BIBTEX_ESCAPED_VALUE_CHARS = frozenset("&%_$#")


def _validate_bibtex_value(value: str, *, field: str) -> None:
    depth = 0
    trailing_backslashes = 0
    for index, ch in enumerate(value):
        if ord(ch) < 32 and ch not in "\t\n":
            raise ValueError(f"BibTeX field '{field}' contains an unsupported control character at position {index}.")
        if ch == "\\":
            trailing_backslashes += 1
            continue
        escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch == "{" and not escaped:
            depth += 1
        elif ch == "}" and not escaped:
            if depth == 0:
                raise ValueError(f"BibTeX field '{field}' contains an unmatched closing brace.")
            depth -= 1
    if depth:
        raise ValueError(f"BibTeX field '{field}' contains unbalanced braces.")
    if trailing_backslashes % 2 == 1:
        raise ValueError(f"BibTeX field '{field}' ends with a dangling backslash.")


def _escape_bibtex_value(value: str, *, field: str) -> str:
    _validate_bibtex_value(value, field=field)
    escaped: list[str] = []
    trailing_backslashes = 0
    for ch in value:
        if ch == "\\":
            escaped.append(ch)
            trailing_backslashes += 1
            continue
        is_escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch in _BIBTEX_ESCAPED_VALUE_CHARS and not is_escaped:
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)


def registry_to_bibtex(registry: list[VerifiedPaper]) -> str:
    entries = []
    for paper in registry:
        authors = " and ".join(paper.authors) if paper.authors else "Unknown"
        is_journal = bool(paper.venue and any(token in paper.venue.lower() for token in ["journal", "transactions"]))
        entry_type = "article" if is_journal else "inproceedings"
        venue_field = "journal" if is_journal else "booktitle"
        venue_value = paper.venue or "Unknown Venue"
        def render_entry(bibtex_key: str) -> str:
            lines = [
                f"@{entry_type}{{{bibtex_key},",
                f"  title = {{{_escape_bibtex_value(paper.title, field='title')}}},",
                f"  author = {{{_escape_bibtex_value(authors, field='author')}}},",
                f"  year = {{{_escape_bibtex_value(str(paper.year or ''), field='year')}}},",
                f"  {venue_field} = {{{_escape_bibtex_value(venue_value, field=venue_field)}}},",
            ]
            if paper.url:
                lines.append(f"  url = {{{_escape_bibtex_value(paper.url, field='url')}}},")
            if paper.external_ids.get("DOI"):
                lines.append(f"  doi = {{{_escape_bibtex_value(paper.external_ids['DOI'], field='doi')}}},")
            lines.append("}")
            return "\n".join(lines)

        for bibtex_key in [paper.bibtex_key, *paper.alias_bibtex_keys]:
            if not bibtex_key:
                continue
            entries.append(render_entry(bibtex_key))
    return "\n\n".join(entries) + ("\n" if entries else "")


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
