from __future__ import annotations

import json
import re
from pathlib import Path

from paperorchestra.orchestra.omx_public_hashing import _sha256_json
from paperorchestra.orchestra.state import NextAction, OrchestraState

VALID_SLUG_RE = re.compile(r"^po-[0-9a-f]{12}$")
PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")


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
    if not VALID_SLUG_RE.fullmatch(slug):
        return False
    return not any(marker in slug.upper() for marker in PRIVATE_MARKERS)


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
