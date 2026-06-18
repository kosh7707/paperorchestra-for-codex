from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.orchestra.state import NextAction, OrchestraState

ALLOWED_SKILL_SURFACES = {
    "$autoresearch",
    "$autoresearch-goal",
    "$deep-interview",
    "$ralplan",
    "$ralph",
    "$ultraqa",
    "$trace",
}

_VALID_SLUG = re.compile(r"^po-[0-9a-f]{12}$")
_VALID_PUBLIC_REASON = re.compile(r"^[a-z0-9_:-]{1,96}$")
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")


def _validate_skill_surface(surface: str) -> None:
    if surface not in ALLOWED_SKILL_SURFACES:
        raise ValueError(f"Unsupported planned OMX skill surface: {surface!r}")


def _public_payload(value: Any) -> Any:
    if hasattr(value, "to_public_dict"):
        return value.to_public_dict()
    if isinstance(value, dict):
        return _jsonable_without_private_values(value)
    if isinstance(value, (list, tuple)):
        return [_public_payload(item) for item in value]
    return value


def _jsonable_without_private_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("private_") or key_text in {"raw_text", "prompt", "argv", "executable_command"}:
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _jsonable_without_private_values(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable_without_private_values(item) for item in value]
    return value


def _default_slug(action: NextAction, state: OrchestraState) -> str:
    seed = _sha256_json(
        {
            "action_type": action.action_type,
            "reason": action.reason,
            "cwd": state.cwd,
            "session_id": state.session_id,
            "manuscript_sha256": state.manuscript_sha256,
        }
    )
    return f"po-{seed[:12]}"


def _valid_public_slug(slug: str) -> bool:
    if not _VALID_SLUG.fullmatch(slug):
        return False
    if any(marker in slug.upper() for marker in _PRIVATE_MARKERS):
        return False
    return True


def _artifact_refs_from_stdout(stdout: str) -> list[str]:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return []
    mission = payload.get("mission") if isinstance(payload, dict) else None
    if not isinstance(mission, dict):
        return []
    refs: list[str] = []
    for key in ("mission_path", "rubric_path", "ledger_path", "completion_path"):
        value = mission.get(key)
        if isinstance(value, str):
            refs.append(value)
    return refs


def _artifact_refs_are_contained(refs: list[str], slug: str) -> bool:
    prefix = f".omx/goals/autoresearch/{slug}/"
    for ref in refs:
        path = Path(ref)
        if path.is_absolute() or ".." in path.parts:
            return False
        if not ref.startswith(prefix):
            return False
    return True


def _has_required_goal_refs(refs: list[str], slug: str) -> bool:
    required = {
        f".omx/goals/autoresearch/{slug}/mission.json",
        f".omx/goals/autoresearch/{slug}/rubric.md",
        f".omx/goals/autoresearch/{slug}/ledger.jsonl",
    }
    return required.issubset(set(refs))


def _public_input_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"topic", "rubric", "argv", "prompt", "raw_text"} or key.startswith("private_"):
            result[key] = "<redacted>"
        else:
            result[key] = value
    return result


def _public_reason(reason: str) -> str:
    if not _VALID_PUBLIC_REASON.fullmatch(reason):
        return "runtime_only_interactive_surface"
    upper = reason.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        return "runtime_only_interactive_surface"
    if reason.startswith(("/", "~")) or ".." in Path(reason).parts or reason.startswith(("omx ", "$")):
        return "runtime_only_interactive_surface"
    return reason


def _public_unsupported_action_type(action_type: str) -> str:
    upper = action_type.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        return "<unsupported-action>"
    if action_type.startswith(("omx ", "$", "/", "~")) or any(character.isspace() for character in action_type):
        return "<unsupported-action>"
    if ".." in Path(action_type).parts:
        return "<unsupported-action>"
    return action_type


def _sha256_json(value: Any) -> str:
    return _sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
