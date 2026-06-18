from __future__ import annotations

from paperorchestra.research.literature_candidates import build_search_grounded_candidates
from paperorchestra.research.literature_sources import (
    OPENALEX_WORKS_SEARCH,
    _cache_dir,
    _cache_path,
    _http_get_json,
    _openalex_abstract,
    _title_from_openalex,
    _year_from_openalex,
    search_openalex,
    search_semantic_scholar,
)
from paperorchestra.research.literature_verification import mock_verified_paper, serialize_registry, verify_candidate_title

__all__ = [
    "OPENALEX_WORKS_SEARCH",
    "_cache_dir",
    "_cache_path",
    "_http_get_json",
    "_openalex_abstract",
    "_title_from_openalex",
    "_year_from_openalex",
    "build_search_grounded_candidates",
    "mock_verified_paper",
    "search_openalex",
    "search_semantic_scholar",
    "serialize_registry",
    "verify_candidate_title",
]
