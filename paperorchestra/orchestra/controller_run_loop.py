from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.claims import build_claim_graph_from_materials
from paperorchestra.orchestra.controller_state import inspect_orchestra_state
from paperorchestra.orchestra.materials import build_material_inventory, build_source_digest
from paperorchestra.orchestra.omx_evidence import build_research_mission_invocation_evidence
from paperorchestra.orchestra.planner import ActionPlanner
from paperorchestra.orchestra.reference_audit_builder import build_reference_metadata_audit
from paperorchestra.orchestra.research_mission import build_evidence_research_mission
from paperorchestra.orchestra.state import OrchestraState


def run_orchestra_until_blocked(cwd: str | Path | None = None, *, material_path: str | Path | None = None) -> OrchestraState:
    """Run deterministic local orchestration until the next live/external action is needed."""

    state = inspect_orchestra_state(cwd, material_path=material_path)
    if material_path is None or state.facets.material != "inventoried_sufficient" or state.facets.source_digest != "ready":
        return state

    material = Path(material_path)
    if not material.exists():
        return state

    inventory = build_material_inventory(material)
    digest = build_source_digest(inventory)
    reference_audit = build_reference_metadata_audit(material)
    state.evidence_refs.append({"kind": "reference_metadata_audit", "payload": reference_audit.to_public_dict()})
    if reference_audit.status == "fail":
        state.facets.citations = "unknown_refs"
        if "reference_metadata_incomplete" not in state.blocking_reasons:
            state.blocking_reasons.append("reference_metadata_incomplete")
    report = build_claim_graph_from_materials(material, inventory, digest)
    state.evidence_refs.append({"kind": "claim_graph", "payload": report.to_public_dict()})
    if report.ready:
        mission = build_evidence_research_mission(report)
        state.evidence_refs.append({"kind": "evidence_research_mission", "payload": mission.to_public_dict()})
        invocation = build_research_mission_invocation_evidence(mission)
        if invocation is not None:
            state.evidence_refs.append({"kind": "omx_invocation_evidence", "payload": invocation.to_public_dict()})
        state.facets.claims = "candidate"
        if mission.task_count:
            state.facets.evidence = "durable_research_needed" if mission.durable_required else "research_needed"
        if any(citation.status == "unknown_reference" and citation.critical for citation in report.citation_obligations):
            state.facets.citations = "unknown_refs"
        state.blocking_reasons.extend(reason for reason in report.blocking_reasons if reason not in state.blocking_reasons)
        state.refresh_derived_fields()
        state.next_actions = ActionPlanner().plan(state)
    return state


__all__ = ["run_orchestra_until_blocked"]
