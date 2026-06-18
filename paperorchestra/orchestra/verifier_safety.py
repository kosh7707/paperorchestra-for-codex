from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
_FORBIDDEN_KEYS = {"argv", "prompt", "raw_text", "executable_command"}
_RAW_COMMAND_RE = re.compile(
    r"(?:^|\b)omx\s+(?:status|trace|exec|ralph|autoresearch|sparkshell|doctor|state|explore|help|version|setup|update)\b",
    re.IGNORECASE,
)


def _unsafe_reasons(value: Any) -> list[str]:
    reasons: list[str] = []

    def visit(node: Any, *, key: str | None = None) -> None:
        if key in _FORBIDDEN_KEYS:
            reasons.append("forbidden_key")
            return
        if isinstance(node, Mapping):
            for child_key, child_value in node.items():
                visit(child_value, key=str(child_key))
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, str):
            return
        upper = node.upper()
        if any(marker in upper for marker in _PRIVATE_MARKERS):
            reasons.append("private_marker")
        elif _looks_like_absolute_path(node):
            reasons.append("absolute_path")
        elif _RAW_COMMAND_RE.search(node):
            reasons.append("raw_command")

    visit(value)
    return sorted(set(reasons))


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or bool(re.search(r"\s/[A-Za-z0-9_.-]", value))


def _redacted_label(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"redacted-{kind}:{digest[:12]}"
