from __future__ import annotations

from typing import Any

from paperorchestra.reviews.reproducibility_context import ReproducibilityAuditContext
from paperorchestra.reviews.reproducibility_reasons import ReproducibilityReasons


def build_reproducibility_report(
    context: ReproducibilityAuditContext,
    reasons: ReproducibilityReasons,
    *,
    require_live_verification: bool,
) -> dict[str, Any]:
    state = context.state
    return {
        "session_id": state.session_id,
        "verdict": reasons.verdict,
        "reasons": reasons.combined,
        "blocking_reasons": reasons.blocking,
        "warning_reasons": reasons.warnings,
        "source_artifacts": _source_artifacts(context),
        "lane_manifest_summary": context.lane_summary,
        "runtime_parity": context.runtime_parity,
        "provider_identity": context.provider_identity,
        "generation_determinism": _generation_determinism(),
        "latest_provider_name": state.latest_provider_name,
        "latest_runtime_mode": state.latest_runtime_mode,
        "require_live_verification": require_live_verification,
        "verification_invoked": context.verification_invoked,
        "latest_verify_mode": state.latest_verify_mode,
        "latest_verify_fallback_used": state.latest_verify_fallback_used,
        "prompt_trace_file_count": len(context.prompt_files),
        "mock_registry_entry_count": context.mock_registry_count,
        "semantic_scholar_required": bool(context.citation_support_review_provenance.get("semantic_scholar_required")),
        "citation_support_review_live": bool(context.citation_support_review_provenance.get("live")),
        "citation_support_review_provenance": context.citation_support_review_provenance,
        "citation_live_provenance": context.citation_live_provenance,
        "citation_registry_live_verified_count": context.citation_live_provenance.get("live_verified_count", 0),
        "citation_registry_entry_count": context.citation_surface["registry_entry_count"],
        "citation_map_entry_count": context.citation_surface["citation_map_entry_count"],
        "references_bib_entry_count": context.citation_surface["references_bib_entry_count"],
        "citation_artifact_issues": context.citation_surface["issues"],
        "paper_has_mock_watermark": context.paper_has_mock_watermark,
        "validation_warning_count": context.validation_warning_count,
        "validation_warning_reports": context.validation_warning_reports,
        "strict_content_gates": context.strict_content_gates,
        "strict_content_gate_issues": context.strict_content_gate_issues,
        "refinement_compile_preservation_count": context.refinement_compile_preservation_count,
    }


def _source_artifacts(context: ReproducibilityAuditContext) -> dict[str, Any]:
    state = context.state
    fallback_runtime_parity = str(context.session_artifact_dir / "runtime-parity.json") if context.session_artifact_dir else None
    return {
        "paper_full_tex": state.artifacts.paper_full_tex,
        "citation_registry_json": state.artifacts.citation_registry_json,
        "citation_map_json": state.artifacts.citation_map_json,
        "references_bib": state.artifacts.references_bib,
        "latest_provider_identity_json": state.artifacts.latest_provider_identity_json,
        "latest_figure_placement_review_json": state.artifacts.latest_figure_placement_review_json,
        "latest_page_layout_review_json": getattr(state.artifacts, "latest_page_layout_review_json", None),
        "latest_visual_repair_brief_json": getattr(state.artifacts, "latest_visual_repair_brief_json", None),
        "latest_visual_repair_candidate_json": getattr(state.artifacts, "latest_visual_repair_candidate_json", None),
        "latest_runtime_parity_json": state.artifacts.latest_runtime_parity_json or fallback_runtime_parity,
        "latest_compile_report_json": state.artifacts.latest_compile_report_json,
        "latest_prompt_trace_dir": context.prompt_trace_dir,
        "latest_lane_summary_json": state.artifacts.latest_lane_summary_json,
    }


def _generation_determinism() -> dict[str, Any]:
    return {
        "byte_identical_generation_claimed": False,
        "auditability_claimed": True,
        "rationale": (
            "PaperOrchestra reproducibility audits track inputs, provider/runtime identity, "
            "prompt traces, validation results, and artifact health; they do not promise "
            "byte-identical LLM text generation."
        ),
    }
