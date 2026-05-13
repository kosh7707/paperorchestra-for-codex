from __future__ import annotations

from pathlib import Path

from .orchestra_claims import build_claim_graph_from_materials
from .orchestra_materials import build_material_inventory, build_source_digest
from .orchestra_omx import build_research_mission_invocation_evidence
from .orchestra_planner import ActionPlanner
from .orchestra_references import build_reference_metadata_audit
from .orchestra_research import build_evidence_research_mission
from .orchestra_state import OrchestraFacets, OrchestraState, file_sha256
from .session import load_session


def inspect_state(cwd: str | Path | None = None, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
    root = Path(cwd or ".").resolve()
    facets = OrchestraFacets()
    session_id = None
    manuscript_sha256 = None
    blocking_reasons: list[str] = []
    evidence_refs: list[dict[str, object]] = []

    if material_path is not None:
        material = Path(material_path)
        if not material.exists():
            facets.material = "missing"
            blocking_reasons.append("material_path_missing")
        else:
            inventory = build_material_inventory(material)
            digest = build_source_digest(inventory)
            if digest.sufficient:
                facets.material = "inventoried_sufficient"
                facets.source_digest = "ready"
                facets.artifacts = "fresh"
            else:
                facets.material = "inventoried_insufficient"
                facets.source_digest = "blocked"
                blocking_reasons.extend(digest.blocking_reasons)
            evidence_refs.extend([
                {"kind": "material_inventory", "payload": inventory.to_public_dict()},
                {"kind": "source_digest", "payload": digest.to_public_dict()},
            ])

    try:
        session = load_session(root)
    except FileNotFoundError:
        session = None

    if session is not None:
        session_id = session.session_id
        facets.session = "initialized"
        if facets.material == "missing":
            facets.material = "inventoried_sufficient"
        paper_path = Path(session.artifacts.paper_full_tex) if session.artifacts.paper_full_tex else None
        pdf_path = Path(session.artifacts.compiled_pdf) if session.artifacts.compiled_pdf else None
        if paper_path and paper_path.exists():
            facets.session = "draft_available"
            facets.writing = "draft_available"
            facets.artifacts = "fresh"
            manuscript_sha256 = file_sha256(paper_path)
        if pdf_path and pdf_path.exists():
            facets.session = "compiled"
            facets.artifacts = "fresh"

    if strict_omx:
        facets.omx = "required_missing"

    state = OrchestraState.new(
        cwd=root,
        session_id=session_id,
        manuscript_sha256=manuscript_sha256,
        facets=facets,
        blocking_reasons=blocking_reasons,
    )
    state.evidence_refs = evidence_refs
    state.next_actions = ActionPlanner().plan(state, strict_omx=strict_omx)
    return state


def run_until_blocked(cwd: str | Path | None = None, *, material_path: str | Path | None = None) -> OrchestraState:
    """Run deterministic local orchestration until the next live/external action is needed."""

    state = inspect_state(cwd, material_path=material_path)
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
