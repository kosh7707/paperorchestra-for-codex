from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from paperorchestra.orchestra.state import NextAction, OrchestraState

EXECUTION_RECORD_SCHEMA_VERSION = "orchestrator-execution-record/1"
ACTION_CAPABILITY_SCHEMA_VERSION = "orchestrator-action-capability/1"
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


def _public_action_type(action_type: str, execution_kind: str) -> str:
    if execution_kind == "unsupported" and _looks_like_command(action_type):
        return "<unsupported-action>"
    return action_type


def _looks_like_command(action_type: str) -> bool:
    return any(character.isspace() for character in action_type) or action_type.startswith(("omx ", "$"))
