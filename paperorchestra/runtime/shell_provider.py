from __future__ import annotations

import json
import os
import random
import shlex
import subprocess
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

    def _record_retry_attempt(self, payload: dict[str, object]) -> None:
        if self.retry_trace_dir is None:
            return
        self.retry_trace_dir.mkdir(parents=True, exist_ok=True)
        path = self.retry_trace_dir / "provider-retry-attempts.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")

    def _run_once(self, prompt: bytes, env: dict[str, str]) -> tuple[int, bytes, bytes, bool]:
        timed_out = False
        with subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        ) as proc:
            try:
                stdout, stderr = proc.communicate(input=prompt, timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                if self.timeout_grace_seconds > 0:
                    try:
                        stdout, stderr = proc.communicate(timeout=self.timeout_grace_seconds)
                        return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", True
                    except subprocess.TimeoutExpired:
                        pass
                proc.kill()
                stdout, stderr = proc.communicate()
            except BaseException:
                proc.kill()
                proc.wait()
                raise
        return proc.returncode if proc.returncode is not None else 1, stdout or b"", stderr or b"", timed_out

    def _failure_detail(self, attempt: int, max_attempts: int, rc: int, stderr_text: str, timed_out: bool) -> str:
        if timed_out:
            timeout = self.timeout_seconds if self.timeout_seconds is not None else "unset"
            return f"attempt {attempt}/{max_attempts}: timed out after {timeout}s + grace {self.timeout_grace_seconds:g}s"
        return f"attempt {attempt}/{max_attempts}: exit {rc}: {stderr_text.strip() or '<empty stderr>'}"

    def _failure_message(self, timed_out: bool, retryable: bool, stderr_text: str) -> str:
        message = "Provider command timed out" if timed_out else "Provider command failed"
        if retryable:
            return message + " after retryable transport handling"
        if timed_out:
            return message + " without retryable transport evidence"
        if is_retryable_provider_stderr(stderr_text) and not self.retry_safe:
            return message + " with retry disabled because PAPERO_PROVIDER_RETRY_SAFE is not set"
        return message

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
