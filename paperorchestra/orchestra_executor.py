from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .orchestra_claims import build_claim_graph_from_materials
from .orchestra_materials import build_material_inventory, build_source_digest
from .orchestra_scorecard import build_scorecard_summary
from .orchestra_state import NextAction, OrchestraState

EXECUTION_RECORD_SCHEMA_VERSION = "orchestrator-execution-record/1"
ACTION_CAPABILITY_SCHEMA_VERSION = "orchestrator-action-capability/1"
LOCAL_SUPPORTED_ACTIONS = {
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
}
FAKE_SUPPORTED_ACTIONS = {
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
    "block",
}
OMX_ACTION_SURFACES = {
    "start_autoresearch": "$autoresearch",
    "start_autoresearch_goal": "$autoresearch-goal",
    "start_deep_interview": "$deep-interview",
    "start_ralplan": "$ralplan",
    "start_ralph": "$ralph",
    "start_ultraqa": "$ultraqa",
    "record_trace_summary": "$trace",
    "run_critic_consensus": "$critic-consensus",
    "run_third_critic_adjudication": "$critic-adjudication",
}
ADAPTER_REQUIRED_ACTIONS = {
    "provide_material",
    "build_evidence_obligations",
    "show_prewriting_notice",
    "re_adjudicate",
    "auto_weaken_or_delete_claim",
    "compile_current",
    "export_results",
    "match_supplied_figures",
}
TERMINAL_BLOCK_ACTIONS = {"block"}
ALLOWED_RISKS = {"low", "medium", "high"}
PRIVATE_KEYS = {"raw_text", "prompt", "argv", "executable_command"}
PUBLIC_SAFE_KEYS = {"private_safe", "private_safe_summary"}


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
        return self.status in {"executed_fake", "executed_local", "executed_omx"}

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
        if action_type in LOCAL_SUPPORTED_ACTIONS:
            return ActionCapability(
                action_type=action_type,
                execution_kind="local_supported",
                adapter_hint="local",
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


class LocalActionExecutor:
    adapter_name = "local"

    def __init__(self, *, material_path: str | Path | None = None) -> None:
        self.material_path = Path(material_path).resolve() if material_path is not None else None

    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        if action.action_type not in LOCAL_SUPPORTED_ACTIONS:
            reason = "material_input_required" if action.action_type == "provide_material" else action.reason
            return ExecutionRecord(
                action_type=action.action_type,
                reason=reason,
                status="unsupported",
                adapter=self.adapter_name,
                evidence_refs=[],
                state_rebuild_required=False,
            )
        if action.action_type == "build_scoring_bundle":
            return self._executed(
                action,
                [
                    {
                        "kind": "scorecard_summary",
                        "payload": build_scorecard_summary(state),
                    }
                ],
            )

        material = self._material_path()
        if material is None:
            return self._blocked(action, "material_path_missing")

        inventory = build_material_inventory(material)
        inventory_ref = {"kind": "material_inventory", "payload": inventory.to_public_dict()}
        if action.action_type == "inspect_material":
            return self._executed(action, [inventory_ref])

        digest = build_source_digest(inventory)
        digest_ref = {"kind": "source_digest", "payload": digest.to_public_dict()}
        if action.action_type == "build_source_digest":
            return self._executed(action, [inventory_ref, digest_ref])

        if action.action_type == "build_claim_graph":
            if not digest.sufficient:
                return self._blocked(action, "source_digest_not_ready", [inventory_ref, digest_ref])
            report = build_claim_graph_from_materials(material, inventory, digest)
            report_ref = {"kind": "claim_graph", "payload": report.to_public_dict()}
            status = "executed_local" if report.ready else "blocked"
            return ExecutionRecord(
                action_type=action.action_type,
                reason=action.reason if report.ready else "claim_graph_not_ready",
                status=status,
                adapter=self.adapter_name,
                evidence_refs=[inventory_ref, digest_ref, report_ref],
                state_rebuild_required=True,
            )

        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="unsupported",
            adapter=self.adapter_name,
            evidence_refs=[],
            state_rebuild_required=False,
        )

    def _material_path(self) -> Path | None:
        if self.material_path is None or not self.material_path.exists():
            return None
        return self.material_path

    def _executed(self, action: NextAction, evidence_refs: list[dict[str, Any]]) -> ExecutionRecord:
        return ExecutionRecord(
            action_type=action.action_type,
            reason=action.reason,
            status="executed_local",
            adapter=self.adapter_name,
            evidence_refs=evidence_refs,
            state_rebuild_required=True,
        )

    def _blocked(
        self,
        action: NextAction,
        reason: str,
        evidence_refs: list[dict[str, Any]] | None = None,
    ) -> ExecutionRecord:
        return ExecutionRecord(
            action_type=action.action_type,
            reason=reason,
            status="blocked",
            adapter=self.adapter_name,
            evidence_refs=list(evidence_refs or []),
            state_rebuild_required=False,
        )


def _redact_public(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if (key_text.startswith("private_") and key_text not in PUBLIC_SAFE_KEYS) or key_text in PRIVATE_KEYS:
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
