from __future__ import annotations

from typing import Any

from paperorchestra.orchestra.executor import ExecutionRecord
from paperorchestra.orchestra.planner import ActionPlanner
from paperorchestra.orchestra.state import OrchestraState


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
