from __future__ import annotations

AUTO_REPAIR_CODES = {
    "unknown_citation_keys",
    "plot_plan_not_reflected",
    "expected_section_missing",
    "expected_section_too_shallow",
}

SEMI_AUTO_REPAIR_CODES = {
    "unsupported_comparative_claim",
    "numeric_grounding_mismatch",
    "citation_coverage_insufficient",
    "citation_density_policy_failed",
    "high_risk_uncited_claim",
}

FIGURE_REPAIR_CODES = {
    "tail_clump",
    "after_conclusion",
    "far_from_first_reference",
    "wide_figure_mismatch",
}

PAGE_LAYOUT_REVIEW_CODES = {
    "page_layout_review_missing",
    "page_layout_review_stale",
    "page_layout_render_failed",
    "page_layout_render_unavailable",
}

VISUAL_REPAIR_BRIEF_CODES = {
    "visual_layout_repair_brief_needed",
    "visual_layout_repair_candidate_needed",
}

MANUAL_REVIEW_CODES = {
    "placement_hint_missing",
}

HARD_HUMAN_ACTION_CODES = {
    "mock_provider",
    "mock_verification",
    "missing_prompt_trace",
    "placement_hint_missing",
    "pdf_text_scan_unavailable",
}

NON_REVIEWABLE_TIER1_CODES = {
    "prompt_meta_leakage",
}

NON_REVIEWABLE_ACTION_CODES = {
    "final_figure_assets_non_reviewable",
    "section_process_residue_detected",
}

TIER2_CLAIM_CODES = {
    "unsupported_comparative_claim",
    "numeric_grounding_mismatch",
    "citation_coverage_insufficient",
    "unknown_citation_keys",
}

CITATION_SUPPORT_REVIEW_REFRESH_CODES = {
    "citation_support_review_missing",
    "citation_support_review_stale",
    "citation_support_case_coverage_mismatch",
    "citation_support_case_context_mismatch",
}

REVIEW_REFRESH_CODES = {
    "review_score_missing",
    "review_score_stale",
    "review_score_legacy_untrusted",
    "review_schema_invalid",
    "review_axes_incomplete",
    "review_axis_invalid",
    "review_axis_justification_missing",
    "review_summary_missing",
    "review_penalties_missing",
    "review_provenance_missing",
    "review_provenance_legacy_untrusted",
    "review_provenance_stale",
    "review_provenance_stage_mismatch",
}

QA_LOOP_SUPPORTED_HANDLER_CODES = {
    "narrative_plan_missing",
    "claim_map_missing",
    "citation_placement_plan_missing",
    "narrative_plan_stale",
    "claim_map_stale",
    "citation_placement_plan_stale",
    "validation_report_missing",
    "validation_report_stale",
    "figure_placement_review_missing",
    "figure_placement_review_stale",
    *PAGE_LAYOUT_REVIEW_CODES,
    *VISUAL_REPAIR_BRIEF_CODES,
    *CITATION_SUPPORT_REVIEW_REFRESH_CODES,
    "citation_support_evidence_research_needed",
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
    "review_score_missing",
    "review_score_stale",
    "review_score_legacy_untrusted",
    "review_schema_invalid",
    "review_axes_incomplete",
    "review_axis_invalid",
    "review_axis_justification_missing",
    "review_summary_missing",
    "review_penalties_missing",
    "review_provenance_missing",
    "review_provenance_legacy_untrusted",
    "review_provenance_stale",
    "review_provenance_stage_mismatch",
    "review_score_below_threshold",
    "citation_support_critic_failed",
    "citation_coverage_insufficient",
    "critical_unknown_reference",
    "critical_missing_bib_entry",
    "critical_unsupported_citation",
    "critical_citation_support_missing",
    "critical_weak_reference_identity",
    "citation_density_policy_failed",
    "high_risk_uncited_claim",
    "compile_report_missing",
    "compile_report_stale",
    "compile_report_legacy_untrusted",
    "compile_pdf_missing",
    "compile_pdf_stale",
    "compile_not_clean",
    "section_review_missing",
    "section_review_stale",
    "section_review_legacy_untrusted",
    "section_quality_below_threshold",
    "source_material_coverage_insufficient",
    "source_obligations_missing",
    "source_obligations_stale",
}

__all__ = [
    "AUTO_REPAIR_CODES",
    "CITATION_SUPPORT_REVIEW_REFRESH_CODES",
    "FIGURE_REPAIR_CODES",
    "HARD_HUMAN_ACTION_CODES",
    "MANUAL_REVIEW_CODES",
    "NON_REVIEWABLE_ACTION_CODES",
    "NON_REVIEWABLE_TIER1_CODES",
    "PAGE_LAYOUT_REVIEW_CODES",
    "QA_LOOP_SUPPORTED_HANDLER_CODES",
    "REVIEW_REFRESH_CODES",
    "SEMI_AUTO_REPAIR_CODES",
    "TIER2_CLAIM_CODES",
    "VISUAL_REPAIR_BRIEF_CODES",
]
