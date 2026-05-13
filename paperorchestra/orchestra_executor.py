from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .orchestra_state import NextAction, OrchestraState

EXECUTION_RECORD_SCHEMA_VERSION = "orchestrator-execution-record/1"
FAKE_SUPPORTED_ACTIONS = {
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
    "block",
}
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
