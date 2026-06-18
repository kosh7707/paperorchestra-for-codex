from __future__ import annotations

from paperorchestra.orchestra.policy_models import ValidationResult
from paperorchestra.orchestra.state import OrchestraState


class StateValidator:
    def validate(self, state: OrchestraState) -> ValidationResult:
        issues: list[str] = []
        if state.hard_gates.status == "fail" and state.readiness.label == "ready_for_human_finalization":
            issues.append("hard_gate_failure_cannot_be_ready")
        if state.facets.quality in {"near_ready", "human_finalization_candidate"} and state.hard_gates.status == "fail":
            issues.append("score_cannot_override_hard_gate")
        if state.facets.writing == "drafting_allowed" and not _drafting_preconditions_met(state):
            issues.append("drafting_allowed_without_ready_preconditions")
        if state.facets.interaction == "human_needed" and state.facets.evidence in {
            "research_needed",
            "durable_research_needed",
        }:
            issues.append("machine_solvable_gap_misrouted_to_human_needed")
        if state.facets.omx == "required_missing" and state.readiness.label == "ready_for_human_finalization":
            issues.append("strict_omx_missing_evidence_cannot_be_ready")
        if state.facets.citations in {"unknown_refs", "unsupported_critical"} and state.readiness.label == "ready_for_human_finalization":
            issues.append("critical_citation_problem_cannot_be_ready")
        if state.author_override and (
            state.facets.claims == "conflict" or state.facets.evidence in {"unresolved", "blocked"}
        ):
            issues.append("author_override_conflicts_with_evidence")
        return ValidationResult(valid=not issues, issues=issues)


def _drafting_preconditions_met(state: OrchestraState) -> bool:
    return (
        state.facets.material == "inventoried_sufficient"
        and state.facets.source_digest == "ready"
        and state.facets.claims == "validated"
        and state.facets.evidence == "supported"
    )
