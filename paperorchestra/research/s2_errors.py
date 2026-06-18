from __future__ import annotations


class SemanticScholarError(RuntimeError):
    """Raised when Semantic Scholar returns an unusable response."""


class SemanticScholarRateLimitError(SemanticScholarError):
    """Raised for HTTP 429 responses from Semantic Scholar."""


class SemanticScholarApiError(SemanticScholarError):
    """Raised for non-rate-limit API failures."""
