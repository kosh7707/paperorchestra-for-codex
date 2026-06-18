from __future__ import annotations

from paperorchestra.research.s2_client import SemanticScholarClient
from paperorchestra.research.s2_constants import SEMANTIC_SCHOLAR_GRAPH_BASE_URL, SEMANTIC_SCHOLAR_SEARCH_FIELDS
from paperorchestra.research.s2_errors import SemanticScholarApiError, SemanticScholarError, SemanticScholarRateLimitError
from paperorchestra.research.s2_policy import S2RateLimiter, S2RetryPolicy

_DEFAULT_CLIENT: SemanticScholarClient | None = None


def get_default_semantic_scholar_client() -> SemanticScholarClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = SemanticScholarClient()
    return _DEFAULT_CLIENT


def reset_default_semantic_scholar_client() -> None:
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = None


__all__ = [
    "SEMANTIC_SCHOLAR_GRAPH_BASE_URL",
    "SEMANTIC_SCHOLAR_SEARCH_FIELDS",
    "S2RateLimiter",
    "S2RetryPolicy",
    "SemanticScholarApiError",
    "SemanticScholarClient",
    "SemanticScholarError",
    "SemanticScholarRateLimitError",
    "get_default_semantic_scholar_client",
    "reset_default_semantic_scholar_client",
]
