from __future__ import annotations

from typing import Any

from paperorchestra.orchestra.executor import ExecutionRecord
from paperorchestra.orchestra.omx_capabilities import OmxActionCapability
from paperorchestra.orchestra.omx_evidence import (
    _public_input_payload,
    _public_reason,
    _public_unsupported_action_type,
    _sha256_json,
    _sha256_text,
)
from paperorchestra.orchestra.omx_runners import OmxCommandResult
from paperorchestra.orchestra.state import NextAction

OMX_ACTION_EXECUTION_SCHEMA_VERSION = "omx-action-execution/1"
OMX_ACTION_HANDOFF_SCHEMA_VERSION = "omx-action-handoff/1"
OMX_ADAPTER_NAME = "omx"


def blocked_record(action: NextAction, reason: str) -> ExecutionRecord:
    return ExecutionRecord(
        action_type=action.action_type,
        reason=reason,
        status="blocked",
        adapter=OMX_ADAPTER_NAME,
        evidence_refs=[],
        state_rebuild_required=False,
    )


def unsupported_record(action: NextAction) -> ExecutionRecord:
    return ExecutionRecord(
        action_type=_public_unsupported_action_type(action.action_type),
        reason=_public_reason(action.reason),
        status="unsupported",
        adapter=OMX_ADAPTER_NAME,
        evidence_refs=[],
        state_rebuild_required=False,
    )


def handoff_required_record(action: NextAction, capability: OmxActionCapability) -> ExecutionRecord:
    reason = _public_reason(action.reason)
    return ExecutionRecord(
        action_type=action.action_type,
        reason=reason,
        status="handoff_required",
        adapter=OMX_ADAPTER_NAME,
        evidence_refs=[handoff_evidence(action.action_type, reason, capability)],
        state_rebuild_required=False,
    )


def failed_omx_record(
    action: NextAction,
    *,
    surface: str,
    argv: list[str],
    input_payload: dict[str, Any],
    result: OmxCommandResult,
) -> ExecutionRecord:
    return ExecutionRecord(
        action_type=action.action_type,
        reason="omx_command_failed",
        status="failed",
        adapter=OMX_ADAPTER_NAME,
        evidence_refs=[execution_evidence(surface, argv, input_payload, result, [])],
        state_rebuild_required=False,
    )


def executed_omx_record(
    action: NextAction,
    *,
    surface: str,
    argv: list[str],
    input_payload: dict[str, Any],
    result: OmxCommandResult,
    artifact_refs: list[str],
) -> ExecutionRecord:
    return ExecutionRecord(
        action_type=action.action_type,
        reason=_public_reason(action.reason),
        status="executed_omx",
        adapter=OMX_ADAPTER_NAME,
        evidence_refs=[execution_evidence(surface, argv, input_payload, result, artifact_refs)],
        state_rebuild_required=True,
    )


def execution_evidence(
    surface: str,
    argv: list[str],
    input_payload: dict[str, Any],
    result: OmxCommandResult,
    artifact_refs: list[str],
) -> dict[str, Any]:
    payload = {
        "schema_version": OMX_ACTION_EXECUTION_SCHEMA_VERSION,
        "action_type": input_payload.get("action_type"),
        "surface": surface,
        "command_hash": _sha256_json({"surface": surface, "argv": argv}),
        "input_bundle_hash": _sha256_json(_public_input_payload(input_payload)),
        "status": "executed_omx" if result.return_code == 0 else "failed",
        "return_code": result.return_code,
        "stdout_hash": _sha256_text(result.stdout),
        "stderr_hash": _sha256_text(result.stderr) if result.stderr else None,
        "artifact_refs": list(artifact_refs),
        "private_safe": True,
    }
    return {"kind": "omx_action_execution", "payload": payload}


def handoff_evidence(action_type: str, reason: str, capability: OmxActionCapability) -> dict[str, Any]:
    public_summary = {
        "action_type": action_type,
        "surface": capability.surface,
        "capability": capability.capability,
        "reason": reason,
    }
    payload = {
        "schema_version": OMX_ACTION_HANDOFF_SCHEMA_VERSION,
        "action_type": action_type,
        "surface": capability.surface,
        "capability": capability.capability,
        "reason": reason,
        "handoff_summary_hash": _sha256_json(public_summary),
        "private_safe": True,
    }
    return {"kind": "omx_action_handoff", "payload": payload}
