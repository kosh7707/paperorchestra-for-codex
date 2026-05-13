from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .orchestra_claims import build_claim_graph_from_materials
from .orchestra_executor import ActionExecutor, ExecutionRecord
from .orchestra_consensus import CriticConsensus
from .orchestra_loop import FullLoopPlanner, LoopFacts
from .orchestra_materials import build_material_inventory, build_source_digest
from .orchestra_omx import build_research_mission_invocation_evidence
from .orchestra_planner import ActionPlanner
from .orchestra_references import build_reference_metadata_audit
from .orchestra_research import build_evidence_research_mission
from .orchestra_scoring import ScholarlyScore, ScoringInputBundle
from .orchestra_state import OrchestraFacets, OrchestraState, file_sha256
from .session import load_session


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


class OrchestraOrchestrator:
    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd or ".").resolve()

    def inspect_state(self, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
        return _inspect_state(self.cwd, material_path=material_path, strict_omx=strict_omx)

    def run_until_blocked(self, *, material_path: str | Path | None = None) -> OrchestratorRunResult:
        return self._result_from_state(_run_until_blocked(self.cwd, material_path=material_path))

    def plan_full_loop(
        self,
        *,
        material_path: str | Path | None = None,
        state: OrchestraState | None = None,
        scoring_bundle: ScoringInputBundle | None = None,
        score: ScholarlyScore | None = None,
        consensus: CriticConsensus | None = None,
        high_risk_readiness: bool = False,
        compiled: bool = False,
        exported: bool = False,
    ) -> OrchestratorRunResult:
        current = state.clone() if state is not None else self.inspect_state(material_path=material_path)
        decision = FullLoopPlanner().plan(
            LoopFacts(
                state=current,
                scoring_bundle=scoring_bundle,
                score=score,
                consensus=consensus,
                high_risk_readiness=high_risk_readiness,
                compiled=compiled,
                exported=exported,
            )
        )
        planned_state = decision.state
        planned_state.next_actions = decision.actions
        return OrchestratorRunResult(
            state=planned_state,
            execution="bounded_full_loop_plan",
            action_taken="none",
            execution_record=None,
        )

    def step(
        self,
        *,
        material_path: str | Path | None = None,
        objective: str | None = None,
        execute: bool = False,
        executor: ActionExecutor | None = None,
    ) -> OrchestratorRunResult:
        state = self.inspect_state(material_path=material_path)
        state.next_actions = ActionPlanner().plan(state, objective=objective)
        if not execute:
            return self._result_from_state(state)
        if executor is None:
            raise ValueError("Explicit ActionExecutor is required when execute=True.")
        if not state.next_actions:
            return OrchestratorRunResult(
                state=state,
                execution="bounded_fake_execution",
                action_taken="none",
                execution_record=None,
            )
        action = state.next_actions[0]
        protected_snapshot = state.to_dict(include_private=True)
        record = executor.execute(action, state)
        if state.to_dict(include_private=True) != protected_snapshot:
            raise ValueError("ActionExecutor must not mutate OrchestraState during bounded execution.")
        if record.evidence_refs:
            state.evidence_refs.append(
                {
                    "kind": "orchestrator_execution_record",
                    "payload": record.to_public_dict(),
                }
            )
        _apply_local_execution_record(state, record.to_public_dict())
        return OrchestratorRunResult(
            state=state,
            execution=_execution_label(record),
            action_taken=action.action_type,
            execution_record=record,
        )

    def _result_from_state(self, state: OrchestraState) -> OrchestratorRunResult:
        return OrchestratorRunResult(state=state)


def inspect_state(cwd: str | Path | None = None, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
    return OrchestraOrchestrator(cwd).inspect_state(material_path=material_path, strict_omx=strict_omx)


def _inspect_state(cwd: str | Path | None = None, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
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
    return OrchestraOrchestrator(cwd).run_until_blocked(material_path=material_path).state


def _execution_label(record: ExecutionRecord) -> str:
    if record.adapter == "local":
        return "bounded_local_execution"
    if record.adapter == "fake":
        return "bounded_fake_execution"
    return "bounded_step_execution"


def _apply_local_execution_record(state: OrchestraState, record_public: dict[str, Any]) -> None:
    if record_public.get("adapter") != "local" or record_public.get("status") != "executed_local":
        return
    action_type = record_public.get("action_type")
    if action_type == "build_source_digest":
        if not _apply_source_digest_transition(state, record_public):
            return
    elif action_type == "build_claim_graph":
        if not _apply_claim_graph_transition(state, record_public):
            return
    elif action_type == "inspect_material":
        return
    else:
        return
    state.refresh_derived_fields()
    state.next_actions = ActionPlanner().plan(state)


def _apply_source_digest_transition(state: OrchestraState, record_public: dict[str, Any]) -> bool:
    payload = _first_evidence_payload(record_public, "source_digest")
    if not _valid_source_digest_payload(payload):
        return False
    state.facets.material = "inventoried_sufficient"
    state.facets.source_digest = "ready"
    state.facets.artifacts = "fresh"
    return True


def _apply_claim_graph_transition(state: OrchestraState, record_public: dict[str, Any]) -> bool:
    payload = _first_evidence_payload(record_public, "claim_graph")
    if not _valid_claim_graph_payload(payload):
        return False
    state.facets.claims = "candidate"
    evidence_obligations = payload.get("evidence_obligations", [])
    citation_obligations = payload.get("citation_obligations", [])
    if any(
        isinstance(item, dict)
        and item.get("criticality") == "high"
        and item.get("status") == "research_needed"
        for item in evidence_obligations
    ):
        state.facets.evidence = "research_needed"
    if any(
        isinstance(item, dict)
        and item.get("critical") is True
        and item.get("status") == "unknown_reference"
        for item in citation_obligations
    ):
        state.facets.citations = "unknown_refs"
    for reason in payload.get("blocking_reasons", []):
        if isinstance(reason, str) and reason not in state.blocking_reasons:
            state.blocking_reasons.append(reason)
    return True


def _first_evidence_payload(record_public: dict[str, Any], kind: str) -> dict[str, Any] | None:
    evidence_refs = record_public.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        return None
    for ref in evidence_refs:
        if not isinstance(ref, dict) or ref.get("kind") != kind:
            continue
        payload = ref.get("payload")
        return payload if isinstance(payload, dict) else None
    return None


def _valid_source_digest_payload(payload: dict[str, Any] | None) -> bool:
    return bool(
        payload
        and payload.get("schema_version") == "source-digest/1"
        and payload.get("sufficient") is True
        and payload.get("private_safe_summary") is True
    )


def _valid_claim_graph_payload(payload: dict[str, Any] | None) -> bool:
    return bool(
        payload
        and payload.get("schema_version") == "claim-graph/1"
        and payload.get("ready") is True
        and isinstance(payload.get("evidence_obligations"), list)
        and isinstance(payload.get("citation_obligations"), list)
        and payload.get("private_safe_summary") is True
    )


def _run_until_blocked(cwd: str | Path | None = None, *, material_path: str | Path | None = None) -> OrchestraState:
    """Run deterministic local orchestration until the next live/external action is needed."""

    state = _inspect_state(cwd, material_path=material_path)
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
