from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from paperorchestra.runtime.provider_base import ProviderError


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
