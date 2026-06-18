from __future__ import annotations

from paperorchestra.orchestra.claim_records import CitationObligation, ClaimCandidate, ClaimGraphReport, EvidenceObligation
from paperorchestra.orchestra.research import build_evidence_research_mission


def _claim(**overrides: object) -> ClaimCandidate:
    data = {
        "claim_id": "C1",
        "claim_type": "method",
        "graph_role": "root",
        "criticality": "medium",
        "text_sha256": "sha256:claim",
        "text_label": "claim-label",
        "source_label": "source-label",
        "source_sha256": "sha256:source",
    }
    data.update(overrides)
    return ClaimCandidate(**data)


def _graph(claim: ClaimCandidate, *, evidence_status: str = "missing", citation_status: str = "not_checked"):
    return ClaimGraphReport(
        schema_version="claim-graph/1",
        status="candidate",
        ready=True,
        claim_count=1,
        claims=[claim],
        evidence_obligations=[
            EvidenceObligation("E1", claim.claim_id, evidence_status, claim.criticality, machine_solvable=True)
        ],
        citation_obligations=[CitationObligation("R1", claim.claim_id, citation_status, critical=True)],
    )


def test_evidence_research_mission_routes_durable_high_risk_claims_to_goal_surface() -> None:
    claim = _claim(claim_type="novelty", criticality="high")

    mission = build_evidence_research_mission(_graph(claim, evidence_status="durable_research_needed"))

    assert mission.status == "durable_research_planned"
    assert mission.desired_surface == "$autoresearch-goal"
    assert mission.durable_required is True
    assert {task.desired_surface for task in mission.tasks} == {"$autoresearch-goal"}


def test_evidence_research_mission_reports_no_research_for_supported_graph() -> None:
    mission = build_evidence_research_mission(_graph(_claim(), evidence_status="supported", citation_status="supported"))

    assert mission.status == "no_research_needed"
    assert mission.task_count == 0
    assert mission.tasks == []
