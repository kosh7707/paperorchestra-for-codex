from __future__ import annotations

from paperorchestra.orchestra.omx_public_goal_refs import (
    PRIVATE_MARKERS as _PRIVATE_MARKERS,
    VALID_SLUG_RE as _VALID_SLUG,
    _artifact_refs_are_contained,
    _artifact_refs_from_stdout,
    _default_slug,
    _has_required_goal_refs,
    _valid_public_slug,
)
from paperorchestra.orchestra.omx_public_hashing import _sha256_json, _sha256_text
from paperorchestra.orchestra.omx_public_redaction import _jsonable_without_private_values, _public_input_payload, _public_payload
from paperorchestra.orchestra.omx_public_sanitize import VALID_PUBLIC_REASON_RE as _VALID_PUBLIC_REASON
from paperorchestra.orchestra.omx_public_sanitize import _public_reason, _public_unsupported_action_type

ALLOWED_SKILL_SURFACES = {
    "$autoresearch",
    "$autoresearch-goal",
    "$deep-interview",
    "$ralplan",
    "$ralph",
    "$ultraqa",
    "$trace",
}


def _validate_skill_surface(surface: str) -> None:
    if surface not in ALLOWED_SKILL_SURFACES:
        raise ValueError(f"Unsupported planned OMX skill surface: {surface!r}")

__all__ = [
    "ALLOWED_SKILL_SURFACES",
    "_PRIVATE_MARKERS",
    "_VALID_PUBLIC_REASON",
    "_VALID_SLUG",
    "_artifact_refs_are_contained",
    "_artifact_refs_from_stdout",
    "_default_slug",
    "_has_required_goal_refs",
    "_jsonable_without_private_values",
    "_public_input_payload",
    "_public_payload",
    "_public_reason",
    "_public_unsupported_action_type",
    "_sha256_json",
    "_sha256_text",
    "_valid_public_slug",
    "_validate_skill_surface",
]
