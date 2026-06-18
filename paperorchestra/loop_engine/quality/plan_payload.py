from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from paperorchestra.core.models import utc_now_iso
from .plan_handoff import _human_handoff, _next_ralph_instruction
from .plan_reads import _plan_reads, _quality_eval_summary_for_plan
from .plan_sources import CitationReviewIdentity
from .policy import QA_LOOP_PLAN_SCHEMA_VERSION


@dataclass(frozen=True)
class QualityLoopPlanPayloadInput:
    cwd: str | Path | None
    state: Any
    reproducibility: Mapping[str, Any]
    fidelity: Mapping[str, Any]
    quality_eval: dict[str, Any]
    quality_eval_for_plan: dict[str, Any]
    quality_eval_path: str | Path | None
    actions: list[dict[str, Any]]
    verdict: str
    verdict_rationale: str
    provenance_for_plan: Mapping[str, Any]
    citation_support_review_path: str | Path
    citation_review_identity: CitationReviewIdentity
    operator_packet_path: str | Path
    operator_packet_sha: str | None
    source_obligations_path: str | Path


def build_quality_loop_plan_payload(context: QualityLoopPlanPayloadInput) -> dict[str, Any]:
    action_buckets = _partition_actions(context.actions)
    payload = {
        "schema_version": QA_LOOP_PLAN_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": context.state.session_id,
        "reads": _plan_reads(context.quality_eval_path, context.quality_eval_for_plan),
        "verdict": context.verdict,
        "verdict_rationale": context.verdict_rationale,
        "quality_eval_summary": _quality_eval_summary_for_plan(context.quality_eval_for_plan),
        "next_iteration_target_hash": None,
        "summary": _summary(context, action_buckets),
        "stop_conditions": _stop_conditions(),
        "source_artifacts": _source_artifacts(context),
        "mixed_provenance_acceptance": context.provenance_for_plan.get("mixed_acceptance"),
        "audit_snapshots": {
            "reproducibility": dict(context.reproducibility),
            "fidelity": dict(context.fidelity),
        },
        "blocking_reasons": context.reproducibility.get("blocking_reasons", []),
        "warning_reasons": context.reproducibility.get("warning_reasons", []),
        "repair_actions": context.actions,
        "human_handoff": _human_handoff(context.verdict, context.actions, context.quality_eval),
        "next_ralph_instruction": _next_ralph_instruction(context.verdict, context.actions),
    }
    supervised_handoff = _supervised_handoff(context, action_buckets["human_needed"])
    if supervised_handoff is not None:
        payload["supervised_handoff"] = supervised_handoff
    return payload


def _partition_actions(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "automatic": [action for action in actions if action.get("automation") == "automatic"],
        "semi_auto": [action for action in actions if action.get("automation") == "semi_auto"],
        "human_needed": [action for action in actions if action.get("automation") == "human_needed"],
    }


def _summary(
    context: QualityLoopPlanPayloadInput,
    action_buckets: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    human_needed = action_buckets["human_needed"]
    return {
        "action_count": len(context.actions),
        "automatic_count": len(action_buckets["automatic"]),
        "semi_auto_count": len(action_buckets["semi_auto"]),
        "human_needed_count": len(human_needed),
        "manual_count": len(human_needed),
        "reproducibility_verdict": context.reproducibility.get("verdict"),
        "fidelity_status": context.fidelity.get("overall_status"),
    }


def _stop_conditions() -> dict[str, str]:
    return {
        "ready_for_human_finalization": "Tier 0, 1, and 2 pass; Tier 3 scorecard passes without anti-inflation; provenance is live or explicitly accepted mixed; Tier 4 remains human-owned.",
        "continue": "automatic or semi-automatic repair actions remain and the loop still has iteration budget.",
        "human_needed": "remaining actions require HITL/domain judgment, critic disagreement resolution, provenance acceptance, or Tier 4 ownership.",
        "failed": "budget is exhausted, repeated hard-gate failures show no progress, non-reviewable structural artifacts such as prompt/meta leakage are present, or oscillation/regression makes autonomous continuation unsafe.",
    }


def _source_artifacts(context: QualityLoopPlanPayloadInput) -> dict[str, Any]:
    artifacts = context.state.artifacts
    return {
        "paper_full_tex": artifacts.paper_full_tex,
        "compiled_pdf": artifacts.compiled_pdf,
        "reproducibility_audit": artifacts.latest_reproducibility_json,
        "fidelity_audit": artifacts.latest_fidelity_json,
        "figure_placement_review": artifacts.latest_figure_placement_review_json,
        "latest_validation": artifacts.latest_validation_json,
        "latest_section_review": getattr(artifacts, "latest_section_review_json", None),
        "citation_support_review": str(context.citation_support_review_path),
        "narrative_plan": artifacts.narrative_plan_json,
        "claim_map": artifacts.claim_map_json,
        "citation_placement_plan": artifacts.citation_placement_plan_json,
        "source_obligations": str(context.source_obligations_path),
        "quality_eval": str(context.quality_eval_path) if context.quality_eval_path else None,
        "operator_review_packet": str(context.operator_packet_path) if context.operator_packet_sha else None,
        "citation_review_sha256": context.citation_review_identity.expected_sha256,
        "citation_review_current_sha256": context.citation_review_identity.current_sha256,
        "citation_review_identity_status": context.citation_review_identity.status,
    }


def _supervised_handoff(
    context: QualityLoopPlanPayloadInput,
    human_needed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if context.verdict != "human_needed":
        return None
    return {
        "schema_version": "supervised-handoff/1",
        "operator_feedback_entry": {
            "kind": "metadata_only",
            "source": "codex_operator",
            "not_independent_human_review": True,
            "allowed_entrypoints": [
                "build-operator-review-packet",
                "import-operator-feedback",
                "apply-operator-feedback",
            ],
            "packet_path": str(context.operator_packet_path) if context.operator_packet_sha else None,
            "packet_sha256": context.operator_packet_sha,
        },
        "supervised_budget": {
            "event_type": "operator_feedback_cycle",
            "separate_from_automatic_budget": True,
        },
        "actionable_failure_summary": {
            "owner_categories": _owner_categories(human_needed),
        },
    }


def _owner_categories(human_needed: list[dict[str, Any]]) -> list[str]:
    return sorted({_owner_category(str(action.get("code") or "")) for action in human_needed})


def _owner_category(code: str) -> str:
    lower_code = code.lower()
    if "proof" in lower_code or "security" in lower_code:
        return "proof"
    if "citation" in lower_code or "reference" in lower_code:
        return "bibliography"
    if "benchmark" in lower_code or "experiment" in lower_code:
        return "experiment"
    if "compile" in lower_code or "validation" in lower_code:
        return "implementation"
    return "author"
