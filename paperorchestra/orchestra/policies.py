from __future__ import annotations

from dataclasses import dataclass, field

from paperorchestra.orchestra.state import OrchestraState


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)


class InteractionPolicy:
    def classify_gap(self, *, gap_type: str, criticality: str = "medium") -> str:
        if gap_type in {"citation", "source", "reference", "related_work", "novelty"}:
            return "research_needed" if criticality != "durable" else "durable_research_needed"
        if gap_type in {"claim_strategy", "contribution_framing", "central_conflict"}:
            return "human_needed"
        return "research_needed"


class ReadinessPolicy:
    def apply(self, state: OrchestraState) -> OrchestraState:
        updated = state.clone()
        _append_hard_gate_failures(updated)
        _append_author_override_blocker(updated)
        _append_unique(updated.blocking_reasons, "missing_omx_invocation_evidence", updated.facets.omx == "required_missing")
        _append_unique(updated.blocking_reasons, "placeholder_figure_unresolved", updated.facets.figures == "placeholder_only")
        updated.refresh_derived_fields()
        return updated


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


def _append_hard_gate_failures(state: OrchestraState) -> None:
    if state.hard_gates.status != "fail":
        return
    for failure in state.hard_gates.failures:
        _append_unique(state.blocking_reasons, failure, True)


def _append_author_override_blocker(state: OrchestraState) -> None:
    conflicts = bool(state.author_override and (state.facets.claims == "conflict" or state.facets.evidence in {"unresolved", "blocked"}))
    _append_unique(state.blocking_reasons, "author_override_conflicts_with_evidence", conflicts)


def _append_unique(values: list[str], value: str, condition: bool) -> None:
    if condition and value not in values:
        values.append(value)


def _drafting_preconditions_met(state: OrchestraState) -> bool:
    return (
        state.facets.material == "inventoried_sufficient"
        and state.facets.source_digest == "ready"
        and state.facets.claims == "validated"
        and state.facets.evidence == "supported"
    )

__all__ = ["InteractionPolicy", "ReadinessPolicy", "StateValidator", "ValidationResult"]
