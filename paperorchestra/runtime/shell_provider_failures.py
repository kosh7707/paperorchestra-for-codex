from __future__ import annotations

from paperorchestra.runtime.provider_base import is_retryable_provider_stderr


def provider_failure_detail(
    *,
    attempt: int,
    max_attempts: int,
    rc: int,
    stderr_text: str,
    timed_out: bool,
    timeout_seconds: float | None,
    timeout_grace_seconds: float,
) -> str:
    if timed_out:
        timeout = timeout_seconds if timeout_seconds is not None else "unset"
        return f"attempt {attempt}/{max_attempts}: timed out after {timeout}s + grace {timeout_grace_seconds:g}s"
    return f"attempt {attempt}/{max_attempts}: exit {rc}: {stderr_text.strip() or '<empty stderr>'}"


def provider_failure_message(*, timed_out: bool, retryable: bool, stderr_text: str, retry_safe: bool) -> str:
    message = "Provider command timed out" if timed_out else "Provider command failed"
    if retryable:
        return message + " after retryable transport handling"
    if timed_out:
        return message + " without retryable transport evidence"
    if is_retryable_provider_stderr(stderr_text) and not retry_safe:
        return message + " with retry disabled because PAPERO_PROVIDER_RETRY_SAFE is not set"
    return message
