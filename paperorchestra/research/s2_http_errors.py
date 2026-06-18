from __future__ import annotations

from urllib.error import HTTPError

from paperorchestra.research.s2_errors import SemanticScholarApiError, SemanticScholarError, SemanticScholarRateLimitError


def retry_after_seconds(error: HTTPError) -> float | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def api_error_for_http(error: HTTPError) -> SemanticScholarError:
    if error.code == 429:
        retry_after = retry_after_seconds(error)
        suffix = f" Retry-After={retry_after:g}s." if retry_after is not None else ""
        return SemanticScholarRateLimitError(
            "Semantic Scholar rate-limited the request (HTTP 429). "
            "The client enforces one request per second; retry later or reduce request volume."
            + suffix
        )
    return SemanticScholarApiError(f"Semantic Scholar request failed with HTTP {error.code}.")
