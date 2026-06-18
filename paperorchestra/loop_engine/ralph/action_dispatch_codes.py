from __future__ import annotations

from paperorchestra.loop_engine.quality.policy import CITATION_SUPPORT_REVIEW_REFRESH_CODES, REVIEW_REFRESH_CODES

NARRATIVE_PLAN_CODES = {
    "narrative_plan_missing",
    "claim_map_missing",
    "citation_placement_plan_missing",
    "narrative_plan_stale",
    "claim_map_stale",
    "citation_placement_plan_stale",
}
VALIDATION_REFRESH_CODES = {"validation_report_missing", "validation_report_stale"}
FIGURE_PLACEMENT_REVIEW_CODES = {"figure_placement_review_missing", "figure_placement_review_stale"}
CITATION_SUPPORT_REVIEW_CODES = CITATION_SUPPORT_REVIEW_REFRESH_CODES | {"citation_support_evidence_research_needed"}
CITATION_QUALITY_REFRESH_CODES = {
    "critical_unknown_reference",
    "critical_missing_bib_entry",
    "critical_unsupported_citation",
    "critical_citation_support_missing",
    "critical_weak_reference_identity",
}
CITATION_INTEGRITY_REFRESH_CODES = {
    "rendered_reference_audit_missing",
    "rendered_reference_audit_stale",
    "citation_intent_plan_missing",
    "citation_intent_plan_stale",
    "citation_source_match_missing",
    "citation_source_match_stale",
    "citation_integrity_missing",
    "citation_integrity_stale",
    "citation_critic_missing",
    "citation_critic_stale",
}
COMPILE_CODES = {
    "compile_report_missing",
    "compile_report_stale",
    "compile_report_legacy_untrusted",
    "compile_pdf_missing",
    "compile_pdf_stale",
    "compile_not_clean",
}
SECTION_REVIEW_CODES = {"section_review_missing", "section_review_stale", "section_review_legacy_untrusted"}
SOURCE_OBLIGATION_CODES = {"source_obligations_missing", "source_obligations_stale"}
REFINE_CODES = {
    "review_score_below_threshold",
    "section_quality_below_threshold",
    "source_material_coverage_insufficient",
}
CITATION_REPAIR_CODES = {
    "citation_support_critic_failed",
    "citation_density_policy_failed",
    "citation_coverage_insufficient",
    "high_risk_uncited_claim",
}
