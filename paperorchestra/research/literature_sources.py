from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from paperorchestra.research.s2_api import SemanticScholarClient, SemanticScholarError, get_default_semantic_scholar_client

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
