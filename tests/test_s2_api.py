from __future__ import annotations

from urllib.error import HTTPError

from paperorchestra.research.s2_api import SemanticScholarClient, SemanticScholarRateLimitError
from paperorchestra.research.s2_policy import S2RateLimiter, S2RetryPolicy


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.body


def _no_wait_limiter() -> S2RateLimiter:
    return S2RateLimiter(min_interval_seconds=0, sleep=lambda _: None)


def _no_retry_policy() -> S2RetryPolicy:
    return S2RetryPolicy(max_attempts=1, sleep=lambda _: None)


def test_semantic_scholar_client_search_builds_request_and_injects_key() -> None:
    captured = []

    def opener(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(b'{"data": [{"title": "Paper"}]}')

    client = SemanticScholarClient(
        api_key="secret-key",
        base_url="https://s2.test/graph/v1/",
        timeout_seconds=12,
        rate_limiter=_no_wait_limiter(),
        retry_policy=_no_retry_policy(),
        opener=opener,
    )

    result = client.search_papers("alert triage", limit=3)

    assert result == [{"title": "Paper"}]
    request, timeout = captured[0]
    assert timeout == 12
    assert request.full_url.startswith("https://s2.test/graph/v1/paper/search?")
    assert "query=alert+triage" in request.full_url
    assert "limit=3" in request.full_url
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers["x-api-key"] == "secret-key"


def test_semantic_scholar_client_empty_fallback_marks_fallback_without_leaking_key() -> None:
    def opener(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs={}, fp=None)

    client = SemanticScholarClient(
        api_key="secret-key",
        fallback_mode="empty",
        rate_limiter=_no_wait_limiter(),
        retry_policy=_no_retry_policy(),
        opener=opener,
    )

    payload = client.get_json("/paper/search", {"query": "x"})

    assert payload == {"data": []}
    assert client.last_response_was_fallback is True


def test_semantic_scholar_client_raises_rate_limit_error_without_fallback() -> None:
    def opener(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs={}, fp=None)

    client = SemanticScholarClient(
        api_key="secret-key",
        rate_limiter=_no_wait_limiter(),
        retry_policy=_no_retry_policy(),
        opener=opener,
    )

    try:
        client.get_json("/paper/search", {"query": "x"})
    except SemanticScholarRateLimitError as exc:
        assert "secret-key" not in str(exc)
    else:
        raise AssertionError("expected SemanticScholarRateLimitError")
