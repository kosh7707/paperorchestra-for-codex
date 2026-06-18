from __future__ import annotations

import os
import urllib.request
from typing import Any, Callable
from urllib.error import HTTPError

from paperorchestra.research.s2_constants import SEMANTIC_SCHOLAR_GRAPH_BASE_URL, SEMANTIC_SCHOLAR_SEARCH_FIELDS
from paperorchestra.research.s2_errors import SemanticScholarError
from paperorchestra.research.s2_http_errors import api_error_for_http, retry_after_seconds
from paperorchestra.research.s2_policy import S2RateLimiter, S2RetryPolicy
from paperorchestra.research.s2_request import s2_headers, s2_url
from paperorchestra.research.s2_transport import request_json_with_retries


class SemanticScholarClient:
    """Small, testable wrapper around the Semantic Scholar Graph API."""

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
        return s2_headers(api_key=self.api_key, user_agent=self.user_agent)

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        return s2_url(self.base_url, path, params)

    @staticmethod
    def _retry_after_seconds(error: HTTPError) -> float | None:
        return retry_after_seconds(error)

    @staticmethod
    def _api_error_for_http(error: HTTPError) -> SemanticScholarError:
        return api_error_for_http(error)

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.last_response_was_fallback = False
        payload, was_fallback = request_json_with_retries(
            url=self._url(path, params),
            headers=self._headers(),
            timeout_seconds=self.timeout_seconds,
            opener=self.opener,
            rate_limiter=self.rate_limiter,
            retry_policy=self.retry_policy,
            fallback_mode=self.fallback_mode,
        )
        self.last_response_was_fallback = was_fallback
        return payload

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
