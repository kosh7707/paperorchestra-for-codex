from __future__ import annotations

from pathlib import Path
from typing import Any

REDACTED = "<redacted>"
PRIVATE_PREFIX = "private_"
PRIVATE_KEYS = {"raw_text", "prompt", "argv", "executable_command"}
PUBLIC_SAFE_KEYS = {"private_safe", "private_safe_summary"}


def redact_public(value: Any, *, root: Path) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if (key_text.startswith(PRIVATE_PREFIX) and key_text not in PUBLIC_SAFE_KEYS) or key_text in PRIVATE_KEYS:
                redacted[key_text] = REDACTED
            else:
                redacted[key_text] = redact_public(item, root=root)
        return redacted
    if isinstance(value, list):
        return [redact_public(item, root=root) for item in value]
    if isinstance(value, tuple):
        return [redact_public(item, root=root) for item in value]
    if isinstance(value, str):
        return sanitize_workspace_path(value, root=root)
    return value


def sanitize_workspace_path(value: str, *, root: Path) -> str:
    root_text = str(root)
    if value == root_text:
        return "."
    if value.startswith(root_text + "/"):
        return Path(value).relative_to(root).as_posix()
    if root_text in value:
        return value.replace(root_text, "<workspace>")
    return value


__all__ = ["REDACTED", "redact_public", "sanitize_workspace_path"]
