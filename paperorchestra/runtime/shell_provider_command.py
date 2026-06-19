from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from paperorchestra.runtime.provider_base import ProviderError, is_retryable_provider_stderr
from paperorchestra.runtime.process_timeout import communicate_with_soft_timeout


def parse_shell_provider_command(command: str) -> list[str]:
    try:
        parsed = json.loads(command)
        if isinstance(parsed, list) and parsed and all(isinstance(item, str) for item in parsed):
            argv = parsed
        else:
            raise ProviderError("Provider command JSON must be a non-empty string array.")
    except json.JSONDecodeError:
        argv = shlex.split(command)

    if not argv:
        raise ProviderError("Provider command must not be empty.")

    executable = Path(argv[0]).name
    allowlist = {
        item.strip()
        for item in os.environ.get(
            "PAPERO_ALLOWED_PROVIDER_BINARIES",
            "codex,openai,ollama,llm,claude,gemini",
        ).split(",")
        if item.strip()
    }
    if executable not in allowlist:
        raise ProviderError(
            f"Provider executable '{executable}' is not allowlisted. Set PAPERO_ALLOWED_PROVIDER_BINARIES to opt in."
        )
    return argv


def run_provider_command_once(
    argv: list[str],
    prompt: bytes,
    env: dict[str, str],
    *,
    timeout_seconds: float | None,
    timeout_grace_seconds: float,
) -> tuple[int, bytes, bytes, bool]:
    with subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    ) as proc:
        stdout, stderr, timed_out = communicate_with_soft_timeout(
            proc,
            input_data=prompt,
            timeout_seconds=timeout_seconds,
            grace_seconds=timeout_grace_seconds,
        )
    return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", timed_out


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


__all__ = [
    "parse_shell_provider_command",
    "provider_failure_detail",
    "provider_failure_message",
    "run_provider_command_once",
]
