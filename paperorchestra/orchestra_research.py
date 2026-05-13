from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .orchestra_claims import ClaimCandidate, ClaimGraphReport

DURABLE_RESEARCH_CLAIM_TYPES = {"novelty", "causal"}
RESEARCH_EVIDENCE_STATUSES = {"missing", "research_needed", "durable_research_needed", "unsupported", "unknown"}
RESEARCH_CITATION_STATUSES = {"unknown_reference", "unsupported", "not_checked", "missing"}


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


def build_evidence_research_mission(claim_graph: ClaimGraphReport) -> EvidenceResearchMission:
    if not claim_graph.ready:
        return EvidenceResearchMission(
            schema_version="evidence-research-mission/1",
            status="blocked",
            ready=False,
            blocking_reasons=["claim_graph_not_ready", *claim_graph.blocking_reasons],
        )

    claims_by_id = {claim.claim_id: claim for claim in claim_graph.claims}
    tasks: list[ResearchTask] = []
    for obligation in claim_graph.evidence_obligations:
        if obligation.status not in RESEARCH_EVIDENCE_STATUSES:
            continue
        claim = claims_by_id.get(obligation.claim_id)
        if claim is None:
            continue
        tasks.append(
            _task_for_claim(
                task_id=f"T{len(tasks) + 1}",
                task_type="evidence_support",
                claim=claim,
                obligation_ids=[obligation.obligation_id],
                status=obligation.status,
                reason="evidence_obligation_requires_machine_research",
            )
        )
    for obligation in claim_graph.citation_obligations:
        if obligation.status not in RESEARCH_CITATION_STATUSES:
            continue
        claim = claims_by_id.get(obligation.claim_id)
        if claim is None:
            continue
        tasks.append(
            _task_for_claim(
                task_id=f"T{len(tasks) + 1}",
                task_type="citation_support",
                claim=claim,
                obligation_ids=[obligation.obligation_id],
                status=obligation.status,
                reason="citation_obligation_requires_machine_research",
            )
        )

    if not tasks:
        return EvidenceResearchMission(
            schema_version="evidence-research-mission/1",
            status="no_research_needed",
            ready=True,
            desired_surface=None,
            durable_required=False,
            task_count=0,
            tasks=[],
        )

    durable = any(_requires_durable_research(claims_by_id.get(task.claim_id), task.status) for task in tasks)
    desired_surface = "$autoresearch-goal" if durable else "$autoresearch"
    routed_tasks = [
        ResearchTask(
            task_id=task.task_id,
            task_type=task.task_type,
            claim_id=task.claim_id,
            claim_type=task.claim_type,
            graph_role=task.graph_role,
            criticality=task.criticality,
            claim_text_sha256=task.claim_text_sha256,
            claim_text_label=task.claim_text_label,
            obligation_ids=list(task.obligation_ids),
            status=task.status,
            desired_surface=desired_surface,
            machine_solvable=True,
            reason=task.reason,
        )
        for task in tasks
    ]
    return EvidenceResearchMission(
        schema_version="evidence-research-mission/1",
        status="durable_research_planned" if durable else "research_planned",
        ready=True,
        desired_surface=desired_surface,
        durable_required=durable,
        task_count=len(routed_tasks),
        tasks=routed_tasks,
    )


def _task_for_claim(
    *,
    task_id: str,
    task_type: str,
    claim: ClaimCandidate,
    obligation_ids: list[str],
    status: str,
    reason: str,
) -> ResearchTask:
    return ResearchTask(
        task_id=task_id,
        task_type=task_type,
        claim_id=claim.claim_id,
        claim_type=claim.claim_type,
        graph_role=claim.graph_role,
        criticality=claim.criticality,
        claim_text_sha256=claim.text_sha256,
        claim_text_label=claim.text_label,
        obligation_ids=list(obligation_ids),
        status=status,
        desired_surface=None,
        machine_solvable=True,
        reason=reason,
    )


def _requires_durable_research(claim: ClaimCandidate | None, status: str) -> bool:
    if status == "durable_research_needed":
        return True
    if claim is None:
        return False
    return claim.criticality == "high" and claim.claim_type in DURABLE_RESEARCH_CLAIM_TYPES
