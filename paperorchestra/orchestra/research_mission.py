from __future__ import annotations

from paperorchestra.orchestra.claim_records import ClaimCandidate, ClaimGraphReport
from paperorchestra.orchestra.research_models import EvidenceResearchMission, ResearchTask

DURABLE_RESEARCH_CLAIM_TYPES = {"novelty", "causal"}
RESEARCH_EVIDENCE_STATUSES = {"missing", "research_needed", "durable_research_needed", "unsupported", "unknown"}
RESEARCH_CITATION_STATUSES = {"unknown_reference", "unsupported", "not_checked", "missing"}


def build_evidence_research_mission(claim_graph: ClaimGraphReport) -> EvidenceResearchMission:
    if not claim_graph.ready:
        return EvidenceResearchMission(
            schema_version="evidence-research-mission/1",
            status="blocked",
            ready=False,
            blocking_reasons=["claim_graph_not_ready", *claim_graph.blocking_reasons],
        )

    claims_by_id = {claim.claim_id: claim for claim in claim_graph.claims}
    tasks = _research_tasks_from_claim_graph(claim_graph, claims_by_id)
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
    routed_tasks = [_route_task_to_surface(task, desired_surface) for task in tasks]
    return EvidenceResearchMission(
        schema_version="evidence-research-mission/1",
        status="durable_research_planned" if durable else "research_planned",
        ready=True,
        desired_surface=desired_surface,
        durable_required=durable,
        task_count=len(routed_tasks),
        tasks=routed_tasks,
    )


def _research_tasks_from_claim_graph(
    claim_graph: ClaimGraphReport,
    claims_by_id: dict[str, ClaimCandidate],
) -> list[ResearchTask]:
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
    return tasks


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


def _route_task_to_surface(task: ResearchTask, desired_surface: str) -> ResearchTask:
    return ResearchTask(
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


def _requires_durable_research(claim: ClaimCandidate | None, status: str) -> bool:
    if status == "durable_research_needed":
        return True
    if claim is None:
        return False
    return claim.criticality == "high" and claim.claim_type in DURABLE_RESEARCH_CLAIM_TYPES
