from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Mapping

_FORBIDDEN_KEYS = {"argv", "prompt", "raw_text", "executable_command"}
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_RAW_COMMAND_RE = re.compile(
    r"(?:^|\b)(?:run\s+)?omx\s+(?:status|trace|exec|ralph|autoresearch|sparkshell|doctor|state|explore|help|version|setup|update)\b",
    re.IGNORECASE,
)
REDACTED = "<redacted>"


def _reject_forbidden_keys(value: Mapping[str, Any], *, gate_id: str) -> None:
    for key, item in value.items():
        if str(key) in _FORBIDDEN_KEYS:
            raise ValueError(f"Unsafe evidence key for {gate_id}: {key}")
        if isinstance(item, Mapping):
            _reject_forbidden_keys(item, gate_id=gate_id)


def _validate_public_string(value: str, *, gate_id: str, field: str) -> None:
    if value == REDACTED:
        return
    upper = value.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        raise ValueError(f"Unsafe private marker in {field} for {gate_id}.")
    if _RAW_COMMAND_RE.search(value):
        raise ValueError(f"Unsafe raw command text in {field} for {gate_id}.")
    if _looks_like_absolute_path(value):
        raise ValueError(f"Unsafe absolute path in {field} for {gate_id}.")


def _validate_kind(value: str, *, gate_id: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_/-]*", value):
        raise ValueError(f"Unsafe evidence kind for {gate_id}.")


def _validate_public_path(value: str, *, gate_id: str) -> None:
    if value == REDACTED:
        return
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Evidence path for {gate_id} must be workspace-relative and contained.")


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or bool(re.search(r"\s/[A-Za-z0-9_.-]", value))
