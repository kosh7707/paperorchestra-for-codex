from __future__ import annotations

from dataclasses import dataclass, field

from .orchestra_state import OrchestraState


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)


class ReadinessPolicy:
    def apply(self, state: OrchestraState) -> OrchestraState:
        updated = state.clone()
        if updated.hard_gates.status == "fail":
            for failure in updated.hard_gates.failures:
                if failure not in updated.blocking_reasons:
                    updated.blocking_reasons.append(failure)
        if updated.author_override and (
            updated.facets.claims == "conflict" or updated.facets.evidence in {"unresolved", "blocked"}
        ):
            if "author_override_conflicts_with_evidence" not in updated.blocking_reasons:
                updated.blocking_reasons.append("author_override_conflicts_with_evidence")
        if updated.facets.omx == "required_missing" and "missing_omx_invocation_evidence" not in updated.blocking_reasons:
            updated.blocking_reasons.append("missing_omx_invocation_evidence")
        if updated.facets.figures == "placeholder_only" and "placeholder_figure_unresolved" not in updated.blocking_reasons:
            updated.blocking_reasons.append("placeholder_figure_unresolved")
        updated.refresh_derived_fields()
        return updated


class StateValidator:
    def validate(self, state: OrchestraState) -> ValidationResult:
        issues: list[str] = []
        if state.hard_gates.status == "fail" and state.readiness.label == "ready_for_human_finalization":
            issues.append("hard_gate_failure_cannot_be_ready")
        if state.facets.quality in {"near_ready", "human_finalization_candidate"} and state.hard_gates.status == "fail":
            issues.append("score_cannot_override_hard_gate")
        if state.facets.writing == "drafting_allowed" and not (
            state.facets.material == "inventoried_sufficient"
            and state.facets.source_digest == "ready"
            and state.facets.claims == "validated"
            and state.facets.evidence == "supported"
        ):
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


class InteractionPolicy:
    def classify_gap(self, *, gap_type: str, criticality: str = "medium") -> str:
        if gap_type in {"citation", "source", "reference", "related_work", "novelty"}:
            return "research_needed" if criticality != "durable" else "durable_research_needed"
        if gap_type in {"claim_strategy", "contribution_framing", "central_conflict"}:
            return "human_needed"
        return "research_needed"
