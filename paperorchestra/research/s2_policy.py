from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class S2RateLimiter:
    """Process-local fixed-window limiter for S2's introductory 1 RPS policy."""

    min_interval_seconds: float = 1.0
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        self._lock = threading.Lock()
        self._last_request_at: float | None = None

    @property
    def last_request_at(self) -> float | None:
        return self._last_request_at

    def wait_for_slot(self) -> float:
        """Wait until another S2 request is allowed and return seconds slept."""
        with self._lock:
            now = self.monotonic()
            slept = 0.0
            if self._last_request_at is not None:
                elapsed = now - self._last_request_at
                remaining = self.min_interval_seconds - elapsed
                if remaining > 0:
                    self.sleep(remaining)
                    slept = remaining
                    now = self.monotonic()
            self._last_request_at = now
            return slept


@dataclass
class S2RetryPolicy:
    """Retry policy for transient Semantic Scholar failures."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 8.0
    max_retry_after_seconds: float = 60.0
    retry_http_statuses: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    retry_on_url_error: bool = True
    retry_on_timeout: bool = True
    retry_on_invalid_json: bool = False
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be non-negative")
        if self.max_retry_after_seconds < 0:
            raise ValueError("max_retry_after_seconds must be non-negative")

    def backoff_delay(self, attempt_index: int, *, retry_after_seconds: float | None = None) -> float:
        if retry_after_seconds is not None:
            return min(retry_after_seconds, self.max_retry_after_seconds)
        delay = self.base_delay_seconds * (self.backoff_multiplier ** max(0, attempt_index - 1))
        return min(delay, self.max_delay_seconds)
