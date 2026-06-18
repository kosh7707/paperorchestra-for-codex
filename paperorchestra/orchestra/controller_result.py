from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.orchestra.executor import ExecutionRecord
from paperorchestra.orchestra.state import OrchestraState


@dataclass
class OrchestratorRunResult:
    state: OrchestraState
    execution: str = "bounded_plan_only"
    action_taken: str = "none"
    execution_record: ExecutionRecord | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "execution": self.execution,
            "action_taken": self.action_taken,
            "state": self.state.to_public_dict(),
            "next_actions": [action.to_dict() for action in self.state.next_actions],
            "blocking_reasons": list(self.state.blocking_reasons),
            "private_safe": True,
        }
        if self.execution_record is not None:
            payload["execution_record"] = self.execution_record.to_public_dict()
            payload["evidence_refs"] = list(payload["execution_record"]["evidence_refs"])
        return payload
