from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    task_type: str
    claim_id: str
    claim_type: str
    graph_role: str
    criticality: str
    claim_text_sha256: str
    claim_text_label: str
    obligation_ids: list[str]
    status: str
    desired_surface: str | None
    machine_solvable: bool = True
    reason: str = "machine_solvable_support_gap"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "graph_role": self.graph_role,
            "criticality": self.criticality,
            "claim_text_sha256": self.claim_text_sha256,
            "claim_text_label": self.claim_text_label,
            "obligation_ids": list(self.obligation_ids),
            "status": self.status,
            "desired_surface": self.desired_surface,
            "machine_solvable": self.machine_solvable,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EvidenceResearchMission:
    schema_version: str
    status: str
    ready: bool
    execution_status: str = "planned_only"
    desired_surface: str | None = None
    durable_required: bool = False
    task_count: int = 0
    tasks: list[ResearchTask] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ready": self.ready,
            "execution_status": self.execution_status,
            "desired_surface": self.desired_surface,
            "durable_required": self.durable_required,
            "task_count": self.task_count,
            "tasks": [task.to_public_dict() for task in self.tasks],
            "blocking_reasons": list(self.blocking_reasons),
            "private_safe_summary": self.private_safe_summary,
        }
