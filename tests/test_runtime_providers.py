from __future__ import annotations

import json
import os
import sys

import pytest

from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import CompletionRequest, ProviderError, TransientProviderError
from paperorchestra.runtime.provider_registry import get_provider
from paperorchestra.runtime.provider_web_capability import (
    provider_supports_web_search,
    provider_web_search_capability_proof,
)
from paperorchestra.runtime.provider_web_command import (
    default_codex_web_provider_command,
    hashlib_sha256_json,
    provider_command_digest,
)
from paperorchestra.runtime.provider_web_prefix import exec_argv_prefix_proves_web_search
from paperorchestra.runtime.shell_provider import ShellProvider
from paperorchestra.runtime.shell_provider_command import run_provider_command_once


def test_run_provider_command_once_forwards_stdin_and_stdout() -> None:
    rc, stdout, stderr, timed_out = run_provider_command_once(
        [
            sys.executable,
            "-c",
            "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data.upper())",
        ],
        b"model input",
        os.environ.copy(),
        timeout_seconds=5,
        timeout_grace_seconds=0,
    )

    assert timed_out is False
    assert rc == 0
    assert stdout == b"MODEL INPUT"
    assert stderr == b""


def test_run_provider_command_once_kills_after_timeout_without_grace() -> None:
    rc, _stdout, _stderr, timed_out = run_provider_command_once(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        b"",
        os.environ.copy(),
        timeout_seconds=0.05,
        timeout_grace_seconds=0,
    )

    assert timed_out is True
    assert rc != 0


def test_run_provider_command_once_allows_grace_completion_after_timeout() -> None:
    rc, stdout, _stderr, timed_out = run_provider_command_once(
        [sys.executable, "-c", "import time; time.sleep(0.1); print('late')"],
        b"",
        os.environ.copy(),
        timeout_seconds=0.02,
        timeout_grace_seconds=1,
    )

    assert timed_out is True
    assert rc == 0
    assert stdout.strip() == b"late"


def test_shell_provider_parses_json_and_shlex_commands(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    monkeypatch.delenv("PAPERO_PROVIDER_TIMEOUT_SECONDS", raising=False)

    json_provider = ShellProvider(command='["codex","--search","exec"]')
    shell_provider = ShellProvider(command="codex --search exec")

    assert json_provider.command_source == "explicit"
    assert json_provider.argv == ["codex", "--search", "exec"]
    assert json_provider.timeout_seconds is None
    assert shell_provider.argv == ["codex", "--search", "exec"]


def test_shell_provider_rejects_non_allowlisted_executable(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)

    with pytest.raises(ProviderError, match="not allowlisted"):
        ShellProvider(command='["curl","https://example.invalid"]')


def test_provider_registry_and_command_digest_keep_public_surface(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)

    mock = get_provider("mock")
    shell = get_provider("shell", command='["codex","--search","exec"]')

    assert isinstance(mock, MockProvider)
    assert isinstance(shell, ShellProvider)
    assert provider_command_digest(shell) == hashlib_sha256_json(["codex", "--search", "exec"])
    assert provider_command_digest(mock) is None

    with pytest.raises(ProviderError, match="Unsupported provider"):
        get_provider("unknown")


def test_default_codex_web_provider_command_uses_optional_env_without_hardcoded_model(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_OMX_MODEL", raising=False)
    monkeypatch.delenv("PAPERO_OMX_REASONING_EFFORT", raising=False)

    assert json.loads(default_codex_web_provider_command()) == ["codex", "--search", "exec", "--skip-git-repo-check"]

    monkeypatch.setenv("PAPERO_OMX_MODEL", "frontier-latest")
    monkeypatch.setenv("PAPERO_OMX_REASONING_EFFORT", "high")

    assert json.loads(default_codex_web_provider_command()) == [
        "codex",
        "--search",
        "exec",
        "--skip-git-repo-check",
        "-m",
        "frontier-latest",
        "-c",
        'model_reasoning_effort="high"',
    ]


def test_direct_codex_web_search_capability_proof_is_auditable(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    provider = ShellProvider(command='["codex","--search","exec","--skip-git-repo-check"]')

    proof = provider_web_search_capability_proof(provider)

    assert exec_argv_prefix_proves_web_search(["codex", "--search", "exec"])
    assert not exec_argv_prefix_proves_web_search(["codex", "exec"])
    assert proof == {
        "provider_capability_proof": "direct-codex-search/1",
        "provider_command_digest": hashlib_sha256_json(provider.argv),
        "web_search_capable": True,
    }
    assert provider_supports_web_search(provider) is True
    assert provider_web_search_capability_proof(MockProvider()) is None


def test_shell_provider_complete_forwards_request_env_and_returns_stdout(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    provider = ShellProvider(command='["codex","--search","exec"]')
    captured = {}

    def fake_run_once(prompt: bytes, env: dict[str, str]) -> tuple[int, bytes, bytes, bool]:
        captured["prompt"] = prompt.decode("utf-8")
        captured["env"] = env
        return 0, b"model output", b"", False

    monkeypatch.setattr(provider, "_run_once", fake_run_once)

    result = provider.complete(
        CompletionRequest(
            system_prompt="system",
            user_prompt="user",
            seed=123,
            temperature=0.2,
            max_output_tokens=456,
        )
    )

    assert result == "model output"
    assert "[SYSTEM]\nsystem" in captured["prompt"]
    assert captured["env"]["PAPERO_PROVIDER_SEED"] == "123"
    assert captured["env"]["PAPERO_PROVIDER_TEMPERATURE"] == "0.2"
    assert captured["env"]["PAPERO_PROVIDER_MAX_OUTPUT_TOKENS"] == "456"


def test_shell_provider_retries_safe_transport_failures_and_records_trace(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_SAFE", "1")
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_JITTER_SECONDS", "0")
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_TRACE_DIR", str(tmp_path))
    provider = ShellProvider(command='["codex","--search","exec"]')
    attempts = iter(
        [
            (1, b"", b"connection lost", False),
            (0, b"ok after retry", b"", False),
        ]
    )
    monkeypatch.setattr(provider, "_run_once", lambda prompt, env: next(attempts))

    assert provider.complete(CompletionRequest(system_prompt="s", user_prompt="u")) == "ok after retry"

    trace = (tmp_path / "provider-retry-attempts.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["status"] for line in trace] == ["failure", "success"]
    assert json.loads(trace[0])["will_replay"] is True


def test_shell_provider_raises_transient_after_retryable_failure_exhausted(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_SAFE", "1")
    monkeypatch.setenv("PAPERO_PROVIDER_RETRY_ATTEMPTS", "0")
    provider = ShellProvider(command='["codex","--search","exec"]')
    monkeypatch.setattr(provider, "_run_once", lambda prompt, env: (1, b"", b"connection lost", False))

    with pytest.raises(TransientProviderError, match="retryable transport"):
        provider.complete(CompletionRequest(system_prompt="s", user_prompt="u"))


def test_provider_wrapper_contract_web_search_capability_proof(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    wrapper = tmp_path / "provider-wrap.sh"
    wrapper.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setenv("PAPERO_ALLOWED_PROVIDER_BINARIES", "codex,bash")
    import hashlib

    wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    contract = {
        "schema_version": "provider-wrapper-contract/1",
        "wrapper_path": str(wrapper),
        "wrapper_sha256": wrapper_sha,
        "modes": {
            "web": {
                "trace_wrapped": True,
                "web_search_capable": True,
                "exec_argv_prefix": ["codex", "--search", "exec"],
            }
        },
    }
    (tmp_path / "provider-wrap.contract.json").write_text(json.dumps(contract), encoding="utf-8")
    provider = ShellProvider(command=json.dumps(["bash", str(wrapper), "web"]))

    proof = provider_web_search_capability_proof(provider)

    assert proof is not None
    assert proof["provider_capability_proof"] == "provider-wrapper-contract/1"
    assert proof["provider_wrapper_path"] == str(wrapper.resolve())
    assert proof["provider_wrapper_sha256"] == wrapper_sha
    assert proof["provider_wrapper_exec_argv_prefix"] == ["codex", "--search", "exec"]
