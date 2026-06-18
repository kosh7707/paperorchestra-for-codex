from __future__ import annotations

from pathlib import Path
from typing import Any

from .history import _failing_codes_from_quality_eval, _tier_statuses
from .utils import _path_ref


def _plan_reads(quality_eval_path: str | Path | None, quality_eval: dict[str, Any]) -> dict[str, Any]:
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}
    citation_support_path = source_artifacts.get("citation_support_review")
    citation_support = {
        "path": str(citation_support_path) if citation_support_path else None,
        "ref": _path_ref(citation_support_path),
        "sha256": source_artifacts.get("citation_review_sha256"),
        "current_sha256": source_artifacts.get("citation_review_current_sha256"),
        "identity_status": source_artifacts.get("citation_review_identity_status"),
    }
    return {
        "quality_eval": _path_ref(quality_eval_path),
        "validation": _path_ref(source_artifacts.get("latest_validation")),
        "fidelity": _path_ref(source_artifacts.get("fidelity_audit")),
        "reproducibility": _path_ref(source_artifacts.get("reproducibility_audit")),
        "figure_placement": _path_ref(source_artifacts.get("figure_placement_review")),
        "citation_support": citation_support,
        "citation_integrity": {
            "audit": _path_ref(source_artifacts.get("citation_integrity_audit")),
            "audit_sha256": source_artifacts.get("citation_integrity_audit_sha256"),
            "critic": _path_ref(source_artifacts.get("citation_integrity_critic")),
            "critic_sha256": source_artifacts.get("citation_integrity_critic_sha256"),
            "rendered_reference_audit": _path_ref(source_artifacts.get("rendered_reference_audit")),
            "rendered_reference_audit_sha256": source_artifacts.get("rendered_reference_audit_sha256"),
        },
        "ralph": {
            "handoff": _path_ref(source_artifacts.get("ralph_handoff")),
            "handoff_sha256": source_artifacts.get("ralph_handoff_sha256"),
            "qa_loop_history": _path_ref(source_artifacts.get("qa_loop_history")),
            "qa_loop_history_sha256": source_artifacts.get("qa_loop_history_sha256"),
        },
        "section_review": _path_ref(source_artifacts.get("latest_section_review")),
        "source_obligations": _path_ref(source_artifacts.get("source_obligations")),
        "narrative_plan": _path_ref(source_artifacts.get("narrative_plan")),
        "claim_map": _path_ref(source_artifacts.get("claim_map")),
        "citation_placement_plan": _path_ref(source_artifacts.get("citation_placement_plan")),
    }


def _quality_eval_summary_for_plan(quality_eval: dict[str, Any]) -> dict[str, Any]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier_statuses = _tier_statuses(quality_eval)
    return {
        "schema_version": quality_eval.get("schema_version"),
        "mode": quality_eval.get("mode"),
        "manuscript_hash": quality_eval.get("manuscript_hash"),
        "tier_statuses": tier_statuses,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "provenance_level": (quality_eval.get("provenance_trust") or {}).get("level"),
        "writer_score_visibility": ((tiers.get("tier_3_scholarly_quality") or {}).get("checks") or {}).get(
            "writer_score_visibility",
            {"status": "pass", "writer_receives_scores": False, "operator_only": True},
        ),
    }
