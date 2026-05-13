from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .orchestra_research import EvidenceResearchMission

ALLOWED_SKILL_SURFACES = {
    "$autoresearch",
    "$autoresearch-goal",
    "$deep-interview",
    "$ralplan",
    "$ralph",
    "$ultraqa",
    "$trace",
}


@dataclass(frozen=True)
class OmxInvocationEvidence:
    schema_version: str
    surface: str
    purpose: str
    strict_required: bool
    command_or_skill_hash: str
    input_bundle_hash: str
    output_ref: str | None = None
    return_code: int | None = None
    status: str = "planned"
    execution_status: str = "planned_only"
    private_material_included: bool = False
    private_safe_summary: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != "omx-invocation-evidence/1":
            raise ValueError("Unsupported OMX invocation evidence schema version.")
        _validate_skill_surface(self.surface)
        if self.status != "planned":
            raise ValueError("Planned OMX invocation evidence cannot report executed/pass status.")
        if self.execution_status != "planned_only":
            raise ValueError("Slice-J OMX invocation evidence must remain planned_only.")
        if self.return_code is not None:
            raise ValueError("Planned OMX invocation evidence cannot include a return code.")
        if self.output_ref is not None:
            raise ValueError("Planned OMX invocation evidence cannot include an output reference.")
        if self.private_material_included:
            raise ValueError("Public planned OMX invocation evidence cannot include private material.")
        if self.private_safe_summary is not True:
            raise ValueError("Public planned OMX invocation evidence must be private-safe.")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "purpose": self.purpose,
            "strict_required": self.strict_required,
            "command_or_skill_hash": self.command_or_skill_hash,
            "input_bundle_hash": self.input_bundle_hash,
            "output_ref": self.output_ref,
            "return_code": self.return_code,
            "status": self.status,
            "execution_status": self.execution_status,
            "private_material_included": self.private_material_included,
            "private_safe_summary": self.private_safe_summary,
        }


def build_planned_omx_invocation_evidence(
    *,
    surface: str,
    purpose: str,
    input_payload: Any,
    strict_required: bool = True,
) -> OmxInvocationEvidence:
    _validate_skill_surface(surface)
    public_input = _public_payload(input_payload)
    return OmxInvocationEvidence(
        schema_version="omx-invocation-evidence/1",
        surface=surface,
        purpose=purpose,
        strict_required=strict_required,
        command_or_skill_hash=_sha256_text(surface),
        input_bundle_hash=_sha256_json(public_input),
        output_ref=None,
        return_code=None,
        status="planned",
        execution_status="planned_only",
        private_material_included=False,
        private_safe_summary=True,
    )


def build_research_mission_invocation_evidence(
    mission: EvidenceResearchMission,
    *,
    purpose: str = "evidence_research",
    strict_required: bool = True,
) -> OmxInvocationEvidence | None:
    if not mission.desired_surface or not mission.task_count:
        return None
    return build_planned_omx_invocation_evidence(
        surface=mission.desired_surface,
        purpose=purpose,
        input_payload=mission,
        strict_required=strict_required,
    )


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
    if isinstance(value, list):
        return [_jsonable_without_private_values(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_without_private_values(item) for item in value]
    return value


def _sha256_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return _sha256_text(rendered)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
