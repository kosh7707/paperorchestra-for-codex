from __future__ import annotations

import os

from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import BaseProvider, ProviderError
from paperorchestra.runtime.provider_web import default_codex_web_provider_command, provider_supports_web_search
from paperorchestra.runtime.shell_provider import ShellProvider


def get_provider(name: str, command: str | None = None) -> BaseProvider:
    normalized = name.strip().lower()
    if normalized == "mock":
        return MockProvider()
    if normalized == "shell":
        return ShellProvider(command=command)
    raise ProviderError(f"Unsupported provider: {name}")


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
