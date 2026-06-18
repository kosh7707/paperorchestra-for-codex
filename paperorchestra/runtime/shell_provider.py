from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

from paperorchestra.runtime.provider_base import (
    BaseProvider,
    CompletionRequest,
    ProviderError,
    TransientProviderError,
    _env_float,
    _env_int,
    is_retryable_provider_stderr,
)
from paperorchestra.runtime.shell_provider_command import parse_shell_provider_command
from paperorchestra.runtime.shell_provider_failures import provider_failure_detail, provider_failure_message
from paperorchestra.runtime.shell_provider_process import run_provider_command_once
from paperorchestra.runtime.shell_provider_trace import record_provider_retry_attempt


class ShellProvider(BaseProvider):
    name = "shell"

    def __init__(self, command: str | None = None, timeout_seconds: float | None = None):
        if command is not None:
            self.command_source = "explicit"
        elif os.environ.get("PAPERO_MODEL_CMD"):
            self.command_source = "PAPERO_MODEL_CMD"
        else:
            self.command_source = "missing"
        self.command = command or os.environ.get("PAPERO_MODEL_CMD")
        if not self.command:
            raise ProviderError("Shell provider requires PAPERO_MODEL_CMD or an explicit command.")
        self.argv = self._parse_command(self.command)
        timeout_value = timeout_seconds if timeout_seconds is not None else os.environ.get("PAPERO_PROVIDER_TIMEOUT_SECONDS")
        self.timeout_seconds = float(timeout_value) if timeout_value not in {None, ""} else None
        self.timeout_grace_seconds = _env_float("PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS", 0.0, minimum=0.0, maximum=3600.0)
        self.retry_attempts = _env_int("PAPERO_PROVIDER_RETRY_ATTEMPTS", 0, minimum=0, maximum=10)
        self.retry_backoff_seconds = _env_float("PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS", 2.0, minimum=0.0, maximum=300.0)
        self.retry_jitter_seconds = _env_float("PAPERO_PROVIDER_RETRY_JITTER_SECONDS", 0.0, minimum=0.0, maximum=300.0)
        self.retry_safe = os.environ.get("PAPERO_PROVIDER_RETRY_SAFE", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.retry_trace_dir = Path(os.environ["PAPERO_PROVIDER_RETRY_TRACE_DIR"]) if os.environ.get("PAPERO_PROVIDER_RETRY_TRACE_DIR") else None

    def _parse_command(self, command: str) -> list[str]:
        return parse_shell_provider_command(command)

    def _record_retry_attempt(self, payload: dict[str, object]) -> None:
        record_provider_retry_attempt(self.retry_trace_dir, payload)

    def _run_once(self, prompt: bytes, env: dict[str, str]) -> tuple[int, bytes, bytes, bool]:
        return run_provider_command_once(
            self.argv,
            prompt,
            env,
            timeout_seconds=self.timeout_seconds,
            timeout_grace_seconds=self.timeout_grace_seconds,
        )

    def _failure_detail(self, attempt: int, max_attempts: int, rc: int, stderr_text: str, timed_out: bool) -> str:
        return provider_failure_detail(
            attempt=attempt,
            max_attempts=max_attempts,
            rc=rc,
            stderr_text=stderr_text,
            timed_out=timed_out,
            timeout_seconds=self.timeout_seconds,
            timeout_grace_seconds=self.timeout_grace_seconds,
        )

    def _failure_message(self, timed_out: bool, retryable: bool, stderr_text: str) -> str:
        return provider_failure_message(
            timed_out=timed_out,
            retryable=retryable,
            stderr_text=stderr_text,
            retry_safe=self.retry_safe,
        )

    def complete(self, request: CompletionRequest) -> str:
        env = os.environ.copy()
        env.pop("PAPERO_PROVIDER_SEED", None)
        env.pop("PAPERO_PROVIDER_TEMPERATURE", None)
        env.pop("PAPERO_PROVIDER_MAX_OUTPUT_TOKENS", None)
        env.update(request.provider_env_overrides())
        prompt = request.combined_prompt().encode("utf-8")
        max_attempts = self.retry_attempts + 1
        failures: list[str] = []
        for attempt in range(1, max_attempts + 1):
            rc, stdout, stderr, timed_out = self._run_once(prompt, env)
            stderr_text = stderr.decode("utf-8", errors="replace")
            stdout_text = stdout.decode("utf-8", errors="replace")
            if rc == 0:
                self._record_retry_attempt({"attempt": attempt, "status": "success", "timed_out": timed_out, "replayed": attempt > 1})
                return stdout_text
            transport_evidence = is_retryable_provider_stderr(stderr_text)
            retryable = self.retry_safe and transport_evidence
            reason = "transport_reconnect" if transport_evidence else ("plain_timeout" if timed_out else "non_retryable_failure")
            failures.append(self._failure_detail(attempt, max_attempts, rc, stderr_text, timed_out))
            self._record_retry_attempt({
                "attempt": attempt,
                "status": "failure",
                "return_code": rc,
                "timed_out": timed_out,
                "reason": reason,
                "retry_safe": self.retry_safe,
                "will_replay": bool(retryable and attempt < max_attempts),
                "stderr_excerpt": stderr_text.strip()[:500],
            })
            if retryable and attempt < max_attempts:
                sleep_seconds = self.retry_backoff_seconds
                if self.retry_jitter_seconds > 0:
                    sleep_seconds += random.uniform(0.0, self.retry_jitter_seconds)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue
            details = "\n".join(failures)
            hint = (
                " Increase PAPERO_PROVIDER_TIMEOUT_SECONDS for slow runs, "
                "PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS for Codex reconnect waits, "
                "PAPERO_PROVIDER_RETRY_ATTEMPTS for prompt replay, and "
                "PAPERO_PROVIDER_RETRY_SAFE=1 only for commands that are safe to replay."
            )
            error_cls = TransientProviderError if retryable else ProviderError
            raise error_cls(f"{self._failure_message(timed_out, retryable, stderr_text)}:\n{details}{hint}")
        raise ProviderError("Provider command failed without producing a result.")

    def fork(self) -> "ShellProvider":
        return ShellProvider(command=json.dumps(self.argv), timeout_seconds=self.timeout_seconds)
