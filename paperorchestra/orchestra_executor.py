from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .orchestra_state import NextAction, OrchestraState

EXECUTION_RECORD_SCHEMA_VERSION = "orchestrator-execution-record/1"
ACTION_CAPABILITY_SCHEMA_VERSION = "orchestrator-action-capability/1"
FAKE_SUPPORTED_ACTIONS = {
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
    "block",
}
POLICY_FAKE_SUPPORTED_ACTIONS = FAKE_SUPPORTED_ACTIONS - {"block"}
OMX_ACTION_SURFACES = {
    "start_autoresearch": "$autoresearch",
    "start_autoresearch_goal": "$autoresearch-goal",
    "start_deep_interview": "$deep-interview",
    "start_ralplan": "$ralplan",
    "start_ralph": "$ralph",
    "start_ultraqa": "$ultraqa",
    "record_trace_summary": "$trace",
}
ADAPTER_REQUIRED_ACTIONS = {
    "build_evidence_obligations",
    "show_prewriting_notice",
    "re_adjudicate",
    "auto_weaken_or_delete_claim",
    "compile_current",
    "export_results",
}
TERMINAL_BLOCK_ACTIONS = {"block"}
ALLOWED_RISKS = {"low", "medium", "high"}
PRIVATE_KEYS = {"raw_text", "prompt", "argv", "executable_command"}


@dataclass
class ExecutionRecord:
    action_type: str
    reason: str
    status: str
    adapter: str
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    state_rebuild_required: bool = True
    private_detail: str | None = field(default=None, repr=False)

    @property
    def succeeded(self) -> bool:
        return self.status == "executed_fake"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_RECORD_SCHEMA_VERSION,
            "action_type": self.action_type,
            "reason": self.reason,
            "status": self.status,
            "adapter": self.adapter,
            "evidence_refs": _redact_public(self.evidence_refs),
            "state_rebuild_required": self.state_rebuild_required,
            "private_safe": True,
        }


class ActionExecutor(Protocol):
    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        ...


@dataclass(frozen=True)
class ActionCapability:
    action_type: str
    execution_kind: str
    adapter_hint: str
    requires_omx: bool = False
    omx_surface: str | None = None
    risk: str = "low"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTION_CAPABILITY_SCHEMA_VERSION,
            "action_type": _public_action_type(self.action_type, self.execution_kind),
            "execution_kind": self.execution_kind,
            "adapter_hint": self.adapter_hint,
            "requires_omx": self.requires_omx,
            "omx_surface": self.omx_surface,
            "risk": self.risk,
            "private_safe": True,
        }


class ActionExecutionPolicy:
    def classify(self, action: NextAction) -> ActionCapability:
        action_type = action.action_type
        risk = _normalize_risk(action.risk)
        if action_type in POLICY_FAKE_SUPPORTED_ACTIONS:
            return ActionCapability(
                action_type=action_type,
                execution_kind="fake_supported",
                adapter_hint="fake",
                risk=risk,
            )
        if action_type in OMX_ACTION_SURFACES:
            return ActionCapability(
                action_type=action_type,
                execution_kind="omx_required",
                adapter_hint="omx",
                requires_omx=True,
                omx_surface=OMX_ACTION_SURFACES[action_type],
                risk=risk,
            )
        if action_type in ADAPTER_REQUIRED_ACTIONS:
            return ActionCapability(
                action_type=action_type,
                execution_kind="adapter_required",
                adapter_hint="paperorchestra",
                risk=risk,
            )
        if action_type in TERMINAL_BLOCK_ACTIONS:
            return ActionCapability(
                action_type=action_type,
                execution_kind="terminal_block",
                adapter_hint="none",
                risk=risk,
            )
        return ActionCapability(
            action_type=action_type,
            execution_kind="unsupported",
            adapter_hint="none",
            risk=risk,
        )


class FakeActionExecutor:
    adapter_name = "fake"

    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        if action.action_type not in FAKE_SUPPORTED_ACTIONS:
            return ExecutionRecord(
                action_type=action.action_type,
                reason=action.reason,
                status="unsupported",
                adapter=self.adapter_name,
                evidence_refs=[],
                state_rebuild_required=False,
            )
        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="executed_fake",
            adapter=self.adapter_name,
            evidence_refs=[
                {
                    "kind": "fake_action_execution",
                    "payload": {
                        "action_type": action.action_type,
                        "reason": action.reason,
                        "state_rebuild_required": True,
                        "private_safe": True,
                    },
                }
            ],
            state_rebuild_required=True,
        )


def _redact_public(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("private_") or key_text in PRIVATE_KEYS:
                redacted[key_text] = "<redacted>"
            else:
                redacted[key_text] = _redact_public(item)
        return redacted
    if isinstance(value, list):
        return [_redact_public(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_public(item) for item in value]
    return value


def _normalize_risk(risk: str) -> str:
    return risk if risk in ALLOWED_RISKS else "unknown"


def _public_action_type(action_type: str, execution_kind: str) -> str:
    if execution_kind == "unsupported" and _looks_like_command(action_type):
        return "<unsupported-action>"
    return action_type


def _looks_like_command(action_type: str) -> bool:
    return any(character.isspace() for character in action_type) or action_type.startswith(("omx ", "$"))
