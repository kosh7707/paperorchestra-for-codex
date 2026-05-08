from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from email.message import Message
from urllib.error import HTTPError, URLError

from paperorchestra.literature import search_semantic_scholar, verify_candidate_title
from paperorchestra.s2_api import (
    S2RateLimiter,
    S2RetryPolicy,
    SemanticScholarApiError,
    SemanticScholarClient,
    SemanticScholarRateLimitError,
    get_default_semantic_scholar_client,
    reset_default_semantic_scholar_client,
)


class FakeResponse:
    def __init__(self, payload: dict | str):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload).encode("utf-8")


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class SemanticScholarClientTests(unittest.TestCase):
    def test_rate_limiter_waits_between_requests(self) -> None:
        clock = FakeClock(100.0)
        limiter = S2RateLimiter(min_interval_seconds=1.0, monotonic=clock.monotonic, sleep=clock.sleep)

        self.assertEqual(limiter.wait_for_slot(), 0.0)
        clock.now += 0.25
        self.assertAlmostEqual(limiter.wait_for_slot(), 0.75)
        self.assertEqual(clock.sleeps, [0.75])
        self.assertEqual(limiter.last_request_at, 101.0)

    def test_rate_limiter_rejects_negative_interval(self) -> None:
        with self.assertRaises(ValueError):
            S2RateLimiter(min_interval_seconds=-0.1)

    def test_retry_policy_rejects_invalid_values(self) -> None:
        for kwargs in [
            {"max_attempts": 0},
            {"base_delay_seconds": -1},
            {"backoff_multiplier": 0.5},
            {"max_delay_seconds": -1},
            {"max_retry_after_seconds": -1},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                S2RetryPolicy(**kwargs)

    def test_client_rejects_invalid_timeout_and_fallback_mode(self) -> None:
        with self.assertRaises(ValueError):
            SemanticScholarClient(timeout_seconds=0)
        with self.assertRaises(ValueError):
            SemanticScholarClient(fallback_mode="mock")

    def test_client_adds_api_key_header_and_rate_limits(self) -> None:
        clock = FakeClock()
        seen_headers: list[dict[str, str]] = []

        def opener(request, timeout):
            seen_headers.append(dict(request.header_items()))
            return FakeResponse({"data": [{"title": "Paper"}]})

        client = SemanticScholarClient(
            api_key="secret-test-key",
            rate_limiter=S2RateLimiter(1.0, monotonic=clock.monotonic, sleep=clock.sleep),
            opener=opener,
        )

        self.assertEqual(client.search_papers("query", limit=1), [{"title": "Paper"}])
        clock.now += 0.10
        client.search_papers("query 2", limit=1)

        self.assertEqual(clock.sleeps, [0.9])
        self.assertEqual(len(seen_headers), 2)
        self.assertEqual(seen_headers[0].get("X-api-key") or seen_headers[0].get("x-api-key"), "secret-test-key")
        self.assertEqual(seen_headers[0].get("Accept"), "application/json")

    def test_client_uses_environment_api_key_by_default(self) -> None:
        old = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        try:
            os.environ["SEMANTIC_SCHOLAR_API_KEY"] = "env-secret"
            client = SemanticScholarClient(opener=lambda request, timeout: FakeResponse({"data": []}))
            self.assertEqual(client.api_key, "env-secret")
        finally:
            if old is None:
                os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            else:
                os.environ["SEMANTIC_SCHOLAR_API_KEY"] = old

    def test_search_url_encodes_query_limit_and_fields(self) -> None:
        urls: list[str] = []

        def opener(request, timeout):
            urls.append(request.full_url)
            return FakeResponse({"data": []})

        client = SemanticScholarClient(api_key=None, opener=opener)
        client.search_papers("AES GCM", limit=7, fields="title,year")

        self.assertIn("/paper/search?", urls[0])
        self.assertIn("query=AES+GCM", urls[0])
        self.assertIn("limit=7", urls[0])
        self.assertIn("fields=title%2Cyear", urls[0])

    def _http_error(self, url: str, code: int, retry_after: str | None = None) -> HTTPError:
        headers = Message()
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        return HTTPError(url, code, "error", headers, None)

    def test_429_retries_with_retry_after_then_succeeds_without_leaking_key(self) -> None:
        calls = []
        retry_sleep = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise self._http_error(request.full_url, 429, retry_after="2")
            return FakeResponse({"data": [{"title": "Recovered"}]})

        client = SemanticScholarClient(
            api_key="secret-test-key",
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, sleep=retry_sleep.append),
            opener=opener,
        )

        self.assertEqual(client.search_papers("query"), [{"title": "Recovered"}])
        self.assertEqual(len(calls), 2)
        self.assertEqual(retry_sleep, [2.0])

    def test_429_exhaustion_raises_redacted_rate_limit_error(self) -> None:
        def opener(request, timeout):
            raise self._http_error(request.full_url, 429, retry_after="2")

        client = SemanticScholarClient(
            api_key="secret-test-key",
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=1),
            opener=opener,
        )

        with self.assertRaises(SemanticScholarRateLimitError) as ctx:
            client.search_papers("query", limit=1)

        message = str(ctx.exception)
        self.assertIn("HTTP 429", message)
        self.assertIn("Retry-After=2s", message)
        self.assertNotIn("secret-test-key", message)

    def test_retry_after_is_capped(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self._http_error(request.full_url, 429, retry_after="120")
            return FakeResponse({"data": []})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, max_retry_after_seconds=5, sleep=sleeps.append),
            opener=opener,
        )
        client.search_papers("query")
        self.assertEqual(sleeps, [5])

    def test_invalid_retry_after_uses_exponential_backoff(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self._http_error(request.full_url, 429, retry_after="not-a-number")
            return FakeResponse({"data": []})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, base_delay_seconds=1.5, sleep=sleeps.append),
            opener=opener,
        )
        client.search_papers("query")
        self.assertEqual(sleeps, [1.5])

    def test_5xx_retries_with_exponential_backoff(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise self._http_error(request.full_url, 503)
            return FakeResponse({"data": [{"title": "Recovered"}]})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=3, base_delay_seconds=0.5, backoff_multiplier=2, sleep=sleeps.append),
            opener=opener,
        )

        self.assertEqual(client.search_papers("query"), [{"title": "Recovered"}])
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_retry_sleep_and_rate_limiter_both_apply_before_retry_attempt(self) -> None:
        clock = FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self._http_error(request.full_url, 503)
            return FakeResponse({"data": []})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(1.0, monotonic=clock.monotonic, sleep=clock.sleep),
            retry_policy=S2RetryPolicy(max_attempts=2, base_delay_seconds=0.2, sleep=clock.sleep),
            opener=opener,
        )

        client.search_papers("query")

        self.assertEqual(calls, 2)
        self.assertEqual(clock.sleeps, [0.2, 0.8])

    def test_backoff_delay_is_capped_for_repeated_5xx(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls < 4:
                raise self._http_error(request.full_url, 503)
            return FakeResponse({"data": []})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(
                max_attempts=4,
                base_delay_seconds=2,
                backoff_multiplier=10,
                max_delay_seconds=5,
                sleep=sleeps.append,
            ),
            opener=opener,
        )

        client.search_papers("query")

        self.assertEqual(sleeps, [2, 5, 5])

    def test_400_does_not_retry(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            raise self._http_error(request.full_url, 400)

        client = SemanticScholarClient(rate_limiter=S2RateLimiter(0), retry_policy=S2RetryPolicy(max_attempts=3), opener=opener)
        with self.assertRaises(SemanticScholarApiError):
            client.search_papers("bad query")
        self.assertEqual(calls, 1)

    def test_url_error_retries_when_enabled(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise URLError("temporary DNS failure")
            return FakeResponse({"data": [{"title": "Recovered"}]})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, sleep=sleeps.append),
            opener=opener,
        )
        self.assertEqual(client.search_papers("query"), [{"title": "Recovered"}])
        self.assertEqual(sleeps, [1.0])

    def test_url_error_does_not_retry_when_disabled(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            raise URLError("down")

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=3, retry_on_url_error=False),
            opener=opener,
        )
        with self.assertRaises(SemanticScholarApiError):
            client.search_papers("query")
        self.assertEqual(calls, 1)

    def test_socket_timeout_retries_when_enabled(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise socket.timeout("timed out")
            return FakeResponse({"data": []})

        client = SemanticScholarClient(rate_limiter=S2RateLimiter(0), retry_policy=S2RetryPolicy(max_attempts=2, sleep=lambda _: None), opener=opener)
        self.assertEqual(client.search_papers("query"), [])
        self.assertEqual(calls, 2)

    def test_socket_timeout_exhaustion_raises(self) -> None:
        def opener(request, timeout):
            raise socket.timeout("timed out")

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=1),
            opener=opener,
        )

        with self.assertRaises(SemanticScholarApiError) as ctx:
            client.search_papers("query")

        self.assertIn("timed out", str(ctx.exception))

    def test_invalid_json_raises_by_default_without_retry(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            return FakeResponse("not json")

        client = SemanticScholarClient(rate_limiter=S2RateLimiter(0), retry_policy=S2RetryPolicy(max_attempts=3), opener=opener)
        with self.assertRaises(SemanticScholarApiError):
            client.search_papers("query")
        self.assertEqual(calls, 1)

    def test_invalid_json_can_retry_when_enabled(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return FakeResponse("not json")
            return FakeResponse({"data": [{"title": "Recovered"}]})

        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, retry_on_invalid_json=True, sleep=lambda _: None),
            opener=opener,
        )
        self.assertEqual(client.search_papers("query"), [{"title": "Recovered"}])

    def test_empty_fallback_returns_empty_result_after_exhaustion(self) -> None:
        def opener(request, timeout):
            raise self._http_error(request.full_url, 503)

        client = SemanticScholarClient(
            fallback_mode="empty",
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=2, sleep=lambda _: None),
            opener=opener,
        )
        self.assertEqual(client.search_papers("query"), [])
        self.assertTrue(client.last_response_was_fallback)

    def test_success_after_fallback_resets_fallback_marker(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self._http_error(request.full_url, 503)
            return FakeResponse({"data": [{"title": "Recovered"}]})

        fallback_client = SemanticScholarClient(
            fallback_mode="empty",
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=1),
            opener=opener,
        )
        self.assertEqual(fallback_client.search_papers("query"), [])
        self.assertTrue(fallback_client.last_response_was_fallback)

        success_client = SemanticScholarClient(
            fallback_mode="empty",
            rate_limiter=S2RateLimiter(0),
            retry_policy=S2RetryPolicy(max_attempts=1),
            opener=opener,
        )
        self.assertEqual(success_client.search_papers("query"), [{"title": "Recovered"}])
        self.assertFalse(success_client.last_response_was_fallback)

    def test_non_list_data_is_normalized_to_empty_list(self) -> None:
        client = SemanticScholarClient(rate_limiter=S2RateLimiter(0), opener=lambda request, timeout: FakeResponse({"data": {"bad": "shape"}}))
        self.assertEqual(client.search_papers("query"), [])

    def test_default_client_can_be_reset(self) -> None:
        reset_default_semantic_scholar_client()
        first = get_default_semantic_scholar_client()
        second = get_default_semantic_scholar_client()
        self.assertIs(first, second)
        reset_default_semantic_scholar_client()
        third = get_default_semantic_scholar_client()
        self.assertIsNot(first, third)

    def test_search_semantic_scholar_caches_before_rate_limiter(self) -> None:
        requests = []

        def opener(request, timeout):
            requests.append(request.full_url)
            return FakeResponse({"data": [{"title": "Cached Paper"}]})

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                client = SemanticScholarClient(api_key=None, opener=opener)
                first = search_semantic_scholar("cache me", limit=1, client=client)
                second = search_semantic_scholar("cache me", limit=1, client=client)
            finally:
                os.chdir(old_cwd)

        self.assertEqual(first, [{"title": "Cached Paper"}])
        self.assertEqual(second, [{"title": "Cached Paper"}])
        self.assertEqual(len(requests), 1)

    def test_empty_fallback_result_is_not_cached(self) -> None:
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise self._http_error(request.full_url, 503)
            return FakeResponse({"data": [{"title": "Recovered"}]})

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                first_client = SemanticScholarClient(
                    fallback_mode="empty",
                    rate_limiter=S2RateLimiter(0),
                    retry_policy=S2RetryPolicy(max_attempts=1),
                    opener=opener,
                )
                second_client = SemanticScholarClient(
                    fallback_mode="raise",
                    rate_limiter=S2RateLimiter(0),
                    retry_policy=S2RetryPolicy(max_attempts=1),
                    opener=opener,
                )
                self.assertEqual(search_semantic_scholar("transient", limit=1, client=first_client), [])
                self.assertEqual(search_semantic_scholar("transient", limit=1, client=second_client), [{"title": "Recovered"}])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(calls, 2)

    def test_verify_candidate_title_returns_best_abstracted_match_with_year_bonus(self) -> None:
        sleeps = []
        client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            opener=lambda request, timeout: FakeResponse(
                {
                    "data": [
                        {
                            "paperId": "wrong",
                            "title": "Protected Channel Relations",
                            "year": 1999,
                            "abstract": "Older adjacent paper.",
                            "authors": [{"name": "A. Author"}],
                        },
                        {
                            "paperId": "right",
                            "title": "Protected Channel Interfaces: Relations among Notions and Analysis of Generic Composition",
                            "year": 2000,
                            "publicationDate": "2000-12-01",
                            "venue": "ASIACRYPT",
                            "abstract": "Defines protected-channel design notions and composition.",
                            "authors": [{"name": "Mihir Bellare"}, {"name": "Chanathip Namprempre"}],
                            "citationCount": 1000,
                            "externalIds": {"DOI": "10.example/test"},
                            "url": "https://example.test/paper",
                        },
                    ]
                }
            ),
        )

        paper = verify_candidate_title(
            "Protected Channel Interfaces: Relations among Notions and Analysis of Generic Composition",
            query_hint="Bellare Namprempre 2000 protected-channel design",
            client=client,
            sleep_fn=sleeps.append,
        )

        self.assertIsNotNone(paper)
        assert paper is not None
        self.assertEqual(paper.paper_id, "right")
        self.assertEqual(paper.year, 2000)
        self.assertEqual(paper.venue, "ASIACRYPT")
        self.assertIn("Bellare", paper.authors[0])
        self.assertEqual(paper.title_match_ratio, 100.0)
        self.assertEqual(sleeps, [1.0])

    def test_verify_candidate_title_rejects_missing_abstract_low_ratio_and_cutoff_flags(self) -> None:
        missing_abstract_client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            opener=lambda request, timeout: FakeResponse(
                {"data": [{"paperId": "p1", "title": "Exact Title", "year": 2020, "abstract": ""}]}
            ),
        )
        self.assertIsNone(
            verify_candidate_title(
                "Exact Title",
                client=missing_abstract_client,
                sleep_fn=lambda _: None,
            )
        )

        low_ratio_client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            opener=lambda request, timeout: FakeResponse(
                {"data": [{"paperId": "p2", "title": "Completely Different Paper", "year": 2020, "abstract": "x"}]}
            ),
        )
        self.assertIsNone(
            verify_candidate_title(
                "Exact Title",
                client=low_ratio_client,
                sleep_fn=lambda _: None,
            )
        )

        after_cutoff_client = SemanticScholarClient(
            rate_limiter=S2RateLimiter(0),
            opener=lambda request, timeout: FakeResponse(
                {"data": [{"paperId": "p3", "title": "Post Cutoff Title", "year": 2025, "publicationDate": "2025-01-02", "abstract": "x"}]}
            ),
        )
        paper = verify_candidate_title(
            "Post Cutoff Title",
            cutoff_date="2025-01-01",
            client=after_cutoff_client,
            sleep_fn=lambda _: None,
        )
        self.assertIsNotNone(paper)
        assert paper is not None
        self.assertTrue(paper.is_after_cutoff)


if __name__ == "__main__":
    unittest.main()
