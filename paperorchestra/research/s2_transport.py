from __future__ import annotations

import json
import socket
import urllib.request
from typing import Any, Callable
from urllib.error import HTTPError, URLError

from paperorchestra.research.s2_errors import SemanticScholarApiError, SemanticScholarError
from paperorchestra.research.s2_http_errors import api_error_for_http, retry_after_seconds
from paperorchestra.research.s2_policy import S2RateLimiter, S2RetryPolicy


def request_json_with_retries(
    *,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    opener: Callable[..., Any],
    rate_limiter: S2RateLimiter,
    retry_policy: S2RetryPolicy,
    fallback_mode: str,
) -> tuple[dict[str, Any], bool]:
    last_error: SemanticScholarError | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        request = urllib.request.Request(url, headers=headers)
        rate_limiter.wait_for_slot()
        try:
            with opener(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8")), False
        except HTTPError as exc:
            last_error = api_error_for_http(exc)
            if attempt >= retry_policy.max_attempts or exc.code not in retry_policy.retry_http_statuses:
                return _fallback_payload_or_raise(last_error, fallback_mode)
            _sleep_before_retry(retry_policy, attempt, retry_after_seconds=retry_after_seconds(exc))
        except (TimeoutError, socket.timeout):
            last_error = SemanticScholarApiError("Semantic Scholar request timed out.")
            if attempt >= retry_policy.max_attempts or not retry_policy.retry_on_timeout:
                return _fallback_payload_or_raise(last_error, fallback_mode)
            _sleep_before_retry(retry_policy, attempt)
        except URLError as exc:
            last_error = SemanticScholarApiError(f"Semantic Scholar request failed: {exc.reason}")
            if attempt >= retry_policy.max_attempts or not retry_policy.retry_on_url_error:
                return _fallback_payload_or_raise(last_error, fallback_mode)
            _sleep_before_retry(retry_policy, attempt)
        except json.JSONDecodeError:
            last_error = SemanticScholarApiError("Semantic Scholar returned invalid JSON.")
            if attempt >= retry_policy.max_attempts or not retry_policy.retry_on_invalid_json:
                return _fallback_payload_or_raise(last_error, fallback_mode)
            _sleep_before_retry(retry_policy, attempt)
    return _fallback_payload_or_raise(last_error or SemanticScholarApiError("Semantic Scholar request failed."), fallback_mode)


def _fallback_payload_or_raise(error: SemanticScholarError, fallback_mode: str) -> tuple[dict[str, Any], bool]:
    if fallback_mode == "empty":
        return {"data": []}, True
    raise error


def _sleep_before_retry(
    retry_policy: S2RetryPolicy,
    attempt_index: int,
    *,
    retry_after_seconds: float | None = None,
) -> None:
    delay = retry_policy.backoff_delay(attempt_index, retry_after_seconds=retry_after_seconds)
    if delay > 0:
        retry_policy.sleep(delay)
