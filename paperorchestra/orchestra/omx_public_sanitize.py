from __future__ import annotations

import re
from pathlib import Path

PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
VALID_PUBLIC_REASON_RE = re.compile(r"^[a-z0-9_:-]{1,96}$")


def _public_reason(reason: str) -> str:
    if not VALID_PUBLIC_REASON_RE.fullmatch(reason):
        return "runtime_only_interactive_surface"
    upper = reason.upper()
    if any(marker in upper for marker in PRIVATE_MARKERS):
        return "runtime_only_interactive_surface"
    if reason.startswith(("/", "~")) or ".." in Path(reason).parts or reason.startswith(("omx ", "$")):
        return "runtime_only_interactive_surface"
    return reason


def _public_unsupported_action_type(action_type: str) -> str:
    upper = action_type.upper()
    if any(marker in upper for marker in PRIVATE_MARKERS):
        return "<unsupported-action>"
    if action_type.startswith(("omx ", "$", "/", "~")) or any(character.isspace() for character in action_type):
        return "<unsupported-action>"
    if ".." in Path(action_type).parts:
        return "<unsupported-action>"
    return action_type
