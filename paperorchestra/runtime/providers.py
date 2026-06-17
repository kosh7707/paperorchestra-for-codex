from __future__ import annotations

import json
import os
import random
import shlex
import subprocess
import time
from pathlib import Path

from paperorchestra.runtime.mock_provider import MockProvider
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
            if timed_out:
                failures.append(
                    f"attempt {attempt}/{max_attempts}: timed out after "
                    f"{self.timeout_seconds if self.timeout_seconds is not None else 'unset'}s"
                    f" + grace {self.timeout_grace_seconds:g}s"
                )
            else:
                failures.append(f"attempt {attempt}/{max_attempts}: exit {rc}: {stderr_text.strip() or '<empty stderr>'}")
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
            message = "Provider command failed"
            if timed_out:
                message = "Provider command timed out"
            if retryable:
                message += " after retryable transport handling"
            elif timed_out:
                message += " without retryable transport evidence"
            elif is_retryable_provider_stderr(stderr_text) and not self.retry_safe:
                message += " with retry disabled because PAPERO_PROVIDER_RETRY_SAFE is not set"
            details = "\n".join(failures)
            hint = (
                " Increase PAPERO_PROVIDER_TIMEOUT_SECONDS for slow runs, "
                "PAPERO_PROVIDER_TIMEOUT_GRACE_SECONDS for Codex reconnect waits, "
                "PAPERO_PROVIDER_RETRY_ATTEMPTS for prompt replay, and "
                "PAPERO_PROVIDER_RETRY_SAFE=1 only for commands that are safe to replay."
            )
            error_cls = TransientProviderError if retryable else ProviderError
            raise error_cls(f"{message}:\n{details}{hint}")
        raise ProviderError("Provider command failed without producing a result.")

    def fork(self) -> "ShellProvider":
        return ShellProvider(command=json.dumps(self.argv), timeout_seconds=self.timeout_seconds)


def get_provider(name: str, command: str | None = None) -> BaseProvider:
    normalized = name.strip().lower()
    if normalized == "mock":
        return MockProvider()
    if normalized == "shell":
        return ShellProvider(command=command)
    raise ProviderError(f"Unsupported provider: {name}")


def default_codex_web_provider_command() -> str:
    command = ["codex", "--search", "exec", "--skip-git-repo-check"]
    if model := os.environ.get("PAPERO_OMX_MODEL"):
        command.extend(["-m", model])
    if effort := os.environ.get("PAPERO_OMX_REASONING_EFFORT"):
        command.extend(["-c", f'model_reasoning_effort="{effort}"'])
    return json.dumps(command)


def provider_command_digest(provider: BaseProvider | None) -> str | None:
    if isinstance(provider, ShellProvider):
        return hashlib_sha256_json(provider.argv)
    return None


def hashlib_sha256_json(value: object) -> str:
    import hashlib as _hashlib

    return _hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()


def _read_wrapper_contract(wrapper_path: Path) -> dict[str, object] | None:
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    if not contract_path.exists():
        return None
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def exec_argv_prefix_proves_web_search(prefix: object) -> bool:
    return (
        isinstance(prefix, list)
        and len(prefix) >= 3
        and [str(item) for item in prefix[-2:]] == ["--search", "exec"]
        and all(isinstance(item, str) and item.strip() for item in prefix)
    )


def _contract_wrapper_path(contract_path: Path, payload: dict[str, object]) -> Path | None:
    value = payload.get("wrapper_path")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        recorded_path = Path(value)
        if not recorded_path.is_absolute():
            recorded_path = contract_path.parent / recorded_path
        return recorded_path.resolve()
    except (OSError, RuntimeError):
        return None


def _redacted_exec_argv_prefix_proves_web_search(mode_payload: dict[str, object]) -> bool:
    return (
        mode_payload.get("search_enabled") is True
        and isinstance(mode_payload.get("exec_argv_prefix_label"), str)
        and str(mode_payload.get("exec_argv_prefix_label")).startswith("redacted-exec-argv-prefix:")
        and isinstance(mode_payload.get("exec_argv_prefix_sha256"), str)
        and len(str(mode_payload.get("exec_argv_prefix_sha256"))) == 64
    )


def provider_web_search_capability_proof(provider: BaseProvider) -> dict[str, object] | None:
    """Return auditable web-search capability proof for trusted citation providers.

    Fresh smoke uses a trace wrapper (`bash provider-wrap.sh web`) so prompt/response
    evidence is preserved.  Direct `codex --search exec` remains valid for ordinary
    web-capable shell providers, but wrapper-backed web support is accepted only when
    an adjacent sidecar proves the wrapper path, hash, mode, and inner argv prefix.
    """

    if not isinstance(provider, ShellProvider):
        return None
    argv = provider.argv
    digest = hashlib_sha256_json(argv)
    if len(argv) >= 3 and Path(argv[0]).name == "codex" and argv[1] == "--search" and argv[2] == "exec":
        return {
            "provider_capability_proof": "direct-codex-search/1",
            "provider_command_digest": digest,
            "web_search_capable": True,
        }
    if len(argv) != 3 or Path(argv[0]).name not in {"bash", "sh"} or argv[2] != "web":
        return None
    wrapper_path = Path(argv[1]).resolve()
    if wrapper_path.name != "provider-wrap.sh" or not wrapper_path.exists():
        return None
    contract_path = wrapper_path.with_name("provider-wrap.contract.json")
    payload = _read_wrapper_contract(wrapper_path)
    if not payload or payload.get("schema_version") != "provider-wrapper-contract/1":
        return None
    recorded_path = _contract_wrapper_path(contract_path, payload)
    if recorded_path != wrapper_path:
        return None
    import hashlib as _hashlib

    actual_wrapper_sha = _hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    if payload.get("wrapper_sha256") != actual_wrapper_sha:
        return None
    modes = payload.get("modes")
    mode_payload = modes.get("web") if isinstance(modes, dict) else None
    if not isinstance(mode_payload, dict):
        return None
    if mode_payload.get("trace_wrapped") is not True or mode_payload.get("web_search_capable") is not True:
        return None
    prefix = mode_payload.get("exec_argv_prefix")
    raw_prefix_proves_web = exec_argv_prefix_proves_web_search(prefix)
    redacted_prefix_proves_web = _redacted_exec_argv_prefix_proves_web_search(mode_payload)
    if not (raw_prefix_proves_web or redacted_prefix_proves_web):
        return None
    contract_sha = _hashlib.sha256(contract_path.read_bytes()).hexdigest()
    proof: dict[str, object] = {
        "provider_capability_proof": "provider-wrapper-contract/1",
        "provider_command_digest": digest,
        "provider_contract_path": str(contract_path),
        "provider_contract_sha256": contract_sha,
        "provider_wrapper_path": str(wrapper_path),
        "provider_wrapper_sha256": actual_wrapper_sha,
        "provider_wrapper_mode": "web",
        "web_search_capable": True,
    }
    if raw_prefix_proves_web:
        proof["provider_wrapper_exec_argv_prefix"] = prefix
    else:
        proof["provider_wrapper_exec_argv_prefix_label"] = mode_payload.get("exec_argv_prefix_label")
        proof["provider_wrapper_exec_argv_prefix_sha256"] = mode_payload.get("exec_argv_prefix_sha256")
    return proof

def provider_supports_web_search(provider: BaseProvider) -> bool:
    return provider_web_search_capability_proof(provider) is not None


def get_citation_support_provider(
    name: str,
    *,
    command: str | None = None,
    evidence_mode: str = "heuristic",
) -> BaseProvider | None:
    if evidence_mode in {"heuristic", "source"}:
        return None
    provider_command = command
    if evidence_mode == "web" and name == "shell" and not provider_command and not os.environ.get("PAPERO_MODEL_CMD"):
        provider_command = default_codex_web_provider_command()
    provider = get_provider(name, command=provider_command)
    if evidence_mode == "web" and name == "shell" and command is None and not provider_supports_web_search(provider):
        provider = get_provider(name, command=default_codex_web_provider_command())
    if evidence_mode == "web" and not provider_supports_web_search(provider):
        raise ProviderError(
            "critique --citation-evidence-mode web requires a Codex shell provider command containing --search. "
            "Set PAPERO_MODEL_CMD to a codex --search exec command, pass --provider-command with --search, "
            "or use --citation-evidence-mode model for non-web model review."
        )
    return provider
