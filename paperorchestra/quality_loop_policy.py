from __future__ import annotations

import re

from .boundary import CONTROL_PROSE_PATTERNS

QUALITY_EVAL_SCHEMA_VERSION = "quality-eval/1"
QA_LOOP_PLAN_SCHEMA_VERSION = "qa-loop-plan/2"
QUALITY_MODES = {"draft", "ralph", "claim_safe"}
HISTORY_FILENAME = "qa-loop-history.jsonl"
DEFAULT_MAX_ITERATIONS = 10
BUDGET_CONSUMING_HISTORY_EVENTS = {"qa_loop_step"}
CITATION_SUPPORT_STATUSES = {
    "supported",
    "weakly_supported",
    "unsupported",
    "needs_manual_check",
    "metadata_only",
    "insufficient_evidence",
    "contradicted",
}

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
}

FIGURE_REPAIR_CODES = {
    "tail_clump",
    "after_conclusion",
    "far_from_first_reference",
    "wide_figure_mismatch",
}

MANUAL_REVIEW_CODES = {
    "placement_hint_missing",
}

HARD_HUMAN_ACTION_CODES = {
    "mock_provider",
    "mock_verification",
    "missing_prompt_trace",
    "placement_hint_missing",
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
    "citation_support_review_missing",
    "citation_support_review_stale",
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

REQUIRED_REVIEW_AXES = {
    "coverage_and_completeness",
    "relevance_and_focus",
    "critical_analysis_and_synthesis",
    "positioning_and_novelty",
    "organization_and_writing",
    "citation_practices_and_rigor",
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

LEAKAGE_PATTERNS_ALWAYS = (
    ("caption_intent", re.compile(r"\bcaption\s*intent\b", re.IGNORECASE)),
    ("rendering_brief", re.compile(r"\brendering[_\s-]*brief\b", re.IGNORECASE)),
    ("source_fidelity", re.compile(r"\bsource[_\s-]*fidelity(?:[_\s-]*notes)?\b", re.IGNORECASE)),
    ("internal_visual_prompt", re.compile(r"\binternal\s+visual\s+prompt\b", re.IGNORECASE)),
    ("generation_objective", re.compile(r"\bgeneration\s+objective\b|\binternal\s+generation\s+objective\b", re.IGNORECASE)),
    ("figure_prompt", re.compile(r"\bfigure\s+prompt\b", re.IGNORECASE)),
    ("prompt_meta", re.compile(r"\bprompt\s*/\s*meta\b|\bprompt\s+meta\b", re.IGNORECASE)),
    ("source_boundary_meta", re.compile(r"\bsupplied\s+source\s+(?:boundary|material)\b|\bprovided\s+(?:method\s+)?material\b|\bsource[-\s]+grounded\b|\bsource\s+boundary\b|\bthe\s+draft\s+must\s+preserve\b|\bbenchmark\s+narrative\s+must\s+report\b|\bdraft\s+remains\s+bounded\b|\bdoes\s+not\s+add\s+an\s+external\s+claim\b", re.IGNORECASE)),
    ("skipped_due_to_upstream_fail", re.compile(r"\bskipped_due_to_upstream_fail\b", re.IGNORECASE)),
    ("figure_prompt_slug_specific", re.compile(r"\bfig[_\s-]+(?:prompt|caption|intent|brief|fidelity)\b|\bfig\s+[a-z][a-z0-9_-]*\s+(?:prompt|caption|intent|brief|fidelity)\b", re.IGNORECASE)),
    ("data_block_marker", re.compile(r"\bdata_block\b|<\s*/?\s*DATA_BLOCK\b", re.IGNORECASE)),
    ("reviewer_feedback_block", re.compile(r"\breviewer_feedback\b", re.IGNORECASE)),
    ("score_redaction_marker", re.compile(r"\bscore_redaction\b|\bwriter_blind_to_reviewer_scores\b", re.IGNORECASE)),
    ("ai_disclaimer", re.compile(r"\bas an ai\b", re.IGNORECASE)),
    ("placeholder_text", re.compile(r"\blorem\s+ipsum\b|\bplaceholder\s+(?:figure|image|asset|text|caption)\b", re.IGNORECASE)),
    ("todo_tbd_marker", re.compile(r"\bTODO\b|\bTBD\b|\\todo\b", re.IGNORECASE)),
    ("proof_omitted_marker", re.compile(r"\bproof\s+omitted\b|\bomitted\s+proof\b", re.IGNORECASE)),
    ("insert_figure_marker", re.compile(r"\binsert\s+(?:the\s+)?figure\b|\bfigure\s+to\s+be\s+inserted\b", re.IGNORECASE)),
    ("pipeline_artifact_name", re.compile(r"\bcitation_map\\.json\b|\bsection_writing\b", re.IGNORECASE)),
    ("planning_artifact_name", re.compile(r"\bnarrative_plan(?:\\.json)?\b|\bclaim_map(?:\\.json)?\b|\bcitation_placement_plan(?:\\.json)?\b", re.IGNORECASE)),
    ("writer_brief_artifact_name", re.compile(r"\bauthor[_\s-]*facing[_\s-]*writer[_\s-]*brief\b|\bwriter[_\s-]*brief(?:\\.json)?\b", re.IGNORECASE)),
    ("visible_claim_id", re.compile(r"\bclaim_id\b|\bclaim-\d{3,}\b", re.IGNORECASE)),
    ("process_manuscript_leakage", re.compile(r"\brevised\s+manuscript\b|\bsupplied\s+(?:library|material|technical\s+evidence)\b|\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b|\bbenchmark\s+packet\b|\bempirical\s+packet\b|\bfigures\s+directory\s+is\s+empty\s+in\s+this\s+packet\b|\bquality\s+gate\b|\breview\s+packet\b", re.IGNORECASE)),
) + CONTROL_PROSE_PATTERNS
LEAKAGE_PATTERNS_VISUAL = (
    ("visual_objective_label", re.compile(r"(?m)(?:^|>)\s*Objective\s*:")),
    ("visual_fidelity_label", re.compile(r"(?m)(?:^|>)\s*Fidelity(?:\s+notes)?\s*:")),
    ("plot_prompt", re.compile(r"\bplot\s+prompt\b", re.IGNORECASE)),
)

MODE_THRESHOLDS = {
    "draft": {"overall_min": 0.0, "axis_min": 0.0},
    "ralph": {"overall_min": 70.0, "axis_min": 60.0},
    "claim_safe": {"overall_min": 80.0, "axis_min": 70.0},
}

SECTION_REVIEW_THRESHOLDS = {
    "draft": {"overall_min": 45.0, "section_min": 35.0, "required_fixes_fail": False},
    "ralph": {"overall_min": 70.0, "section_min": 60.0, "required_fixes_fail": True},
    "claim_safe": {"overall_min": 75.0, "section_min": 70.0, "required_fixes_fail": True},
}
