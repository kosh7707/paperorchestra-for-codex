from __future__ import annotations

import hashlib
import json
import os

from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.shell_provider import ShellProvider


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
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()
