from __future__ import annotations

import json
import os
import socket
import urllib.parse
import urllib.request
from typing import Any, Callable

from paperorchestra.research.s2_policy import S2RateLimiter, S2RetryPolicy
from urllib.error import HTTPError, URLError

SEMANTIC_SCHOLAR_GRAPH_BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_SEARCH_FIELDS = "title,year,publicationDate,venue,abstract,authors,citationCount,externalIds,url,paperId"


class SemanticScholarError(RuntimeError):
    """Raised when Semantic Scholar returns an unusable response."""


class SemanticScholarRateLimitError(SemanticScholarError):
    """Raised for HTTP 429 responses from Semantic Scholar."""


class SemanticScholarApiError(SemanticScholarError):
    """Raised for non-rate-limit API failures."""



class SemanticScholarClient:
    """Small, testable wrapper around the Semantic Scholar Graph API.

    The wrapper centralizes API-key injection, 1 RPS throttling, bounded retries,
    JSON decoding, optional explicit fallback, and HTTP error normalization. It
    deliberately keeps the key out of returned errors and logs.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = SEMANTIC_SCHOLAR_GRAPH_BASE_URL,
        timeout_seconds: float = 30.0,
        rate_limiter: S2RateLimiter | None = None,
        retry_policy: S2RetryPolicy | None = None,
        fallback_mode: str = "raise",
        opener: Callable[..., Any] | None = None,
        user_agent: str = "paperorchestra-reconstruction/0.1",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if fallback_mode not in {"raise", "empty"}:
            raise ValueError("fallback_mode must be 'raise' or 'empty'")
        self.api_key = api_key if api_key is not None else os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = rate_limiter if rate_limiter is not None else S2RateLimiter()
        self.retry_policy = retry_policy if retry_policy is not None else S2RetryPolicy()
        self.fallback_mode = fallback_mode
        self.opener = opener if opener is not None else urllib.request.urlopen
        self.user_agent = user_agent
        self.last_response_was_fallback = False

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        normalized_path = path if path.startswith("/") else "/" + path
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        return f"{self.base_url}{normalized_path}" + (f"?{query}" if query else "")

    @staticmethod
    def _retry_after_seconds(error: HTTPError) -> float | None:
        raw = error.headers.get("Retry-After") if error.headers else None
        if not raw:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    @staticmethod
    def _api_error_for_http(error: HTTPError) -> SemanticScholarError:
        if error.code == 429:
            retry_after = SemanticScholarClient._retry_after_seconds(error)
            suffix = f" Retry-After={retry_after:g}s." if retry_after is not None else ""
            return SemanticScholarRateLimitError(
                "Semantic Scholar rate-limited the request (HTTP 429). "
                "The client enforces one request per second; retry later or reduce request volume."
                + suffix
            )
        return SemanticScholarApiError(f"Semantic Scholar request failed with HTTP {error.code}.")

    def _sleep_before_retry(self, attempt_index: int, *, retry_after_seconds: float | None = None) -> None:
        delay = self.retry_policy.backoff_delay(attempt_index, retry_after_seconds=retry_after_seconds)
        if delay > 0:
            self.retry_policy.sleep(delay)

    def _should_retry_http(self, error: HTTPError) -> bool:
        return error.code in self.retry_policy.retry_http_statuses

    def _fallback_payload_or_raise(self, error: SemanticScholarError) -> dict[str, Any]:
        if self.fallback_mode == "empty":
            self.last_response_was_fallback = True
            return {"data": []}
        raise error

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url(path, params)
        last_error: SemanticScholarError | None = None
        self.last_response_was_fallback = False
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            request = urllib.request.Request(url, headers=self._headers())
            self.rate_limiter.wait_for_slot()
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    self.last_response_was_fallback = False
                    return payload
            except HTTPError as exc:
                last_error = self._api_error_for_http(exc)
                if attempt >= self.retry_policy.max_attempts or not self._should_retry_http(exc):
                    return self._fallback_payload_or_raise(last_error)
                self._sleep_before_retry(attempt, retry_after_seconds=self._retry_after_seconds(exc))
            except (TimeoutError, socket.timeout) as exc:
                last_error = SemanticScholarApiError("Semantic Scholar request timed out.")
                if attempt >= self.retry_policy.max_attempts or not self.retry_policy.retry_on_timeout:
                    return self._fallback_payload_or_raise(last_error)
                self._sleep_before_retry(attempt)
            except URLError as exc:
                last_error = SemanticScholarApiError(f"Semantic Scholar request failed: {exc.reason}")
                if attempt >= self.retry_policy.max_attempts or not self.retry_policy.retry_on_url_error:
                    return self._fallback_payload_or_raise(last_error)
                self._sleep_before_retry(attempt)
            except json.JSONDecodeError as exc:
                last_error = SemanticScholarApiError("Semantic Scholar returned invalid JSON.")
                if attempt >= self.retry_policy.max_attempts or not self.retry_policy.retry_on_invalid_json:
                    return self._fallback_payload_or_raise(last_error)
                self._sleep_before_retry(attempt)
        return self._fallback_payload_or_raise(last_error or SemanticScholarApiError("Semantic Scholar request failed."))

    def search_papers(
        self,
        query: str,
        *,
        limit: int = 5,
        fields: str = SEMANTIC_SCHOLAR_SEARCH_FIELDS,
    ) -> list[dict[str, Any]]:
        payload = self.get_json(
            "/paper/search",
            {
                "query": query,
                "limit": limit,
                "fields": fields,
            },
        )
        data = payload.get("data", [])
        return data if isinstance(data, list) else []


_DEFAULT_CLIENT: SemanticScholarClient | None = None


def get_default_semantic_scholar_client() -> SemanticScholarClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = SemanticScholarClient()
    return _DEFAULT_CLIENT


def reset_default_semantic_scholar_client() -> None:
    global _DEFAULT_CLIENT
    _DEFAULT_CLIENT = None
