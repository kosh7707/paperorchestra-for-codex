from __future__ import annotations

from pathlib import Path

from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.provider_web_command import hashlib_sha256_json
from paperorchestra.runtime.provider_web_contract import wrapper_contract_capability_proof
from paperorchestra.runtime.shell_provider import ShellProvider


def provider_web_search_capability_proof(provider: BaseProvider) -> dict[str, object] | None:
    """Return auditable web-search capability proof for trusted citation providers."""

    if not isinstance(provider, ShellProvider):
        return None
    argv = provider.argv
    digest = hashlib_sha256_json(argv)
    if _is_direct_codex_search(argv):
        return {
            "provider_capability_proof": "direct-codex-search/1",
            "provider_command_digest": digest,
            "web_search_capable": True,
        }
    return wrapper_contract_capability_proof(argv, provider_command_digest=digest)


def provider_supports_web_search(provider: BaseProvider) -> bool:
    return provider_web_search_capability_proof(provider) is not None


def _is_direct_codex_search(argv: list[str]) -> bool:
    return len(argv) >= 3 and Path(argv[0]).name == "codex" and argv[1] == "--search" and argv[2] == "exec"
