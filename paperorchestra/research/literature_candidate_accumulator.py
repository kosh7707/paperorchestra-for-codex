from __future__ import annotations

from typing import Any

from paperorchestra.research import dates as _dates
from paperorchestra.research.matching import normalize_title


class CandidateAccumulator:
    def __init__(self, *, cutoff_date: str | None = None) -> None:
        self.payload: dict[str, list[dict[str, Any]]] = {"macro_candidates": [], "micro_candidates": []}
        self._cutoff_date = cutoff_date
        self._seen_titles: set[str] = set()
        self._candidate_index: dict[str, dict[str, Any]] = {}

    def append_candidate(
        self,
        *,
        bucket: str,
        title: str,
        why_relevant: str,
        origin_query: str,
        discovery_source: str,
        year: int | None,
        publication_date: str | None = None,
    ) -> None:
        normalized = normalize_title(title)
        if not normalized:
            return
        if normalized in self._seen_titles:
            self._merge_discovery_source(normalized, discovery_source)
            return
        if not _dates.year_month_passes_cutoff(year, self._cutoff_date, publication_date):
            return
        self._seen_titles.add(normalized)
        candidate = {
            "title_guess": title,
            "why_relevant": why_relevant,
            "origin_query": origin_query,
            "role_guess": "macro" if bucket == "macro_candidates" else "micro",
            "discovery_source": discovery_source,
            "discovery_sources": [discovery_source],
        }
        self.payload[bucket].append(candidate)
        self._candidate_index[normalized] = candidate

    def _merge_discovery_source(self, normalized_title: str, discovery_source: str) -> None:
        existing = self._candidate_index.get(normalized_title)
        if existing is None:
            return
        sources = existing.setdefault("discovery_sources", [])
        if discovery_source not in sources:
            sources.append(discovery_source)
