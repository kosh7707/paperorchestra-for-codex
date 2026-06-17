from __future__ import annotations

import json

import pytest

from paperorchestra.runtime import providers
from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import ProviderError


def test_shell_provider_parses_json_and_shlex_commands(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)
    monkeypatch.delenv("PAPERO_PROVIDER_TIMEOUT_SECONDS", raising=False)

    json_provider = providers.ShellProvider(command='["codex","--search","exec"]')
    shell_provider = providers.ShellProvider(command="codex --search exec")

    assert json_provider.command_source == "explicit"
    assert json_provider.argv == ["codex", "--search", "exec"]
    assert json_provider.timeout_seconds is None
    assert shell_provider.argv == ["codex", "--search", "exec"]


def test_shell_provider_rejects_non_allowlisted_executable(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)

    with pytest.raises(ProviderError, match="not allowlisted"):
        providers.ShellProvider(command='["curl","https://example.invalid"]')


def test_provider_registry_and_command_digest_keep_public_surface(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_MODEL_CMD", raising=False)

    mock = providers.get_provider("mock")
    shell = providers.get_provider("shell", command='["codex","--search","exec"]')

    assert isinstance(mock, MockProvider)
    assert isinstance(shell, providers.ShellProvider)
    assert providers.provider_command_digest(shell) == providers.hashlib_sha256_json(["codex", "--search", "exec"])
    assert providers.provider_command_digest(mock) is None

    with pytest.raises(ProviderError, match="Unsupported provider"):
        providers.get_provider("unknown")


def test_default_codex_web_provider_command_uses_optional_env_without_hardcoded_model(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_OMX_MODEL", raising=False)
    monkeypatch.delenv("PAPERO_OMX_REASONING_EFFORT", raising=False)

    assert json.loads(providers.default_codex_web_provider_command()) == ["codex", "--search", "exec", "--skip-git-repo-check"]

    monkeypatch.setenv("PAPERO_OMX_MODEL", "frontier-latest")
    monkeypatch.setenv("PAPERO_OMX_REASONING_EFFORT", "high")

    assert json.loads(providers.default_codex_web_provider_command()) == [
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
    provider = providers.ShellProvider(command='["codex","--search","exec","--skip-git-repo-check"]')

    proof = providers.provider_web_search_capability_proof(provider)

    assert providers.exec_argv_prefix_proves_web_search(["codex", "--search", "exec"])
    assert not providers.exec_argv_prefix_proves_web_search(["codex", "exec"])
    assert proof == {
        "provider_capability_proof": "direct-codex-search/1",
        "provider_command_digest": providers.hashlib_sha256_json(provider.argv),
        "web_search_capable": True,
    }
    assert providers.provider_supports_web_search(provider) is True
    assert providers.provider_web_search_capability_proof(MockProvider()) is None
