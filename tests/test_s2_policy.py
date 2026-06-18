from __future__ import annotations

from paperorchestra.research.s2_api import S2RateLimiter, S2RetryPolicy
from paperorchestra.research.s2_policy import S2RateLimiter as PolicyLimiter
from paperorchestra.research.s2_policy import S2RetryPolicy as PolicyRetry


def test_s2_policy_reexports_preserve_public_api() -> None:
    assert S2RateLimiter is PolicyLimiter
    assert S2RetryPolicy is PolicyRetry


def test_s2_rate_limiter_waits_for_fixed_window_slot() -> None:
    clock = iter([0.0, 0.2, 1.0])
    sleeps: list[float] = []
    limiter = S2RateLimiter(min_interval_seconds=1.0, monotonic=lambda: next(clock), sleep=sleeps.append)

    assert limiter.wait_for_slot() == 0.0
    assert limiter.wait_for_slot() == 0.8
    assert sleeps == [0.8]


def test_s2_retry_policy_caps_exponential_backoff() -> None:
    policy = S2RetryPolicy(base_delay_seconds=2, max_delay_seconds=3)

    assert policy.backoff_delay(1) == 2
    assert policy.backoff_delay(3) == 3
    assert policy.backoff_delay(3, retry_after_seconds=99) == 60
