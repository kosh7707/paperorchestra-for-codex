from __future__ import annotations

from paperorchestra.loop_engine.quality.policy_actions import (
    AUTO_REPAIR_CODES,
    CITATION_SUPPORT_REVIEW_REFRESH_CODES,
    FIGURE_REPAIR_CODES,
    HARD_HUMAN_ACTION_CODES,
    MANUAL_REVIEW_CODES,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    REVIEW_REFRESH_CODES,
    SEMI_AUTO_REPAIR_CODES,
    TIER2_CLAIM_CODES,
)
from paperorchestra.loop_engine.quality.policy_leakage import LEAKAGE_PATTERNS_ALWAYS, LEAKAGE_PATTERNS_VISUAL

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

REQUIRED_REVIEW_AXES = {
    "coverage_and_completeness",
    "relevance_and_focus",
    "critical_analysis_and_synthesis",
    "positioning_and_novelty",
    "organization_and_writing",
    "citation_practices_and_rigor",
}

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

__all__ = [
    "AUTO_REPAIR_CODES",
    "BUDGET_CONSUMING_HISTORY_EVENTS",
    "CITATION_SUPPORT_REVIEW_REFRESH_CODES",
    "CITATION_SUPPORT_STATUSES",
    "DEFAULT_MAX_ITERATIONS",
    "FIGURE_REPAIR_CODES",
    "HARD_HUMAN_ACTION_CODES",
    "HISTORY_FILENAME",
    "LEAKAGE_PATTERNS_ALWAYS",
    "LEAKAGE_PATTERNS_VISUAL",
    "MANUAL_REVIEW_CODES",
    "MODE_THRESHOLDS",
    "NON_REVIEWABLE_ACTION_CODES",
    "NON_REVIEWABLE_TIER1_CODES",
    "QUALITY_EVAL_SCHEMA_VERSION",
    "QUALITY_MODES",
    "QA_LOOP_PLAN_SCHEMA_VERSION",
    "QA_LOOP_SUPPORTED_HANDLER_CODES",
    "REQUIRED_REVIEW_AXES",
    "REVIEW_REFRESH_CODES",
    "SECTION_REVIEW_THRESHOLDS",
    "SEMI_AUTO_REPAIR_CODES",
    "TIER2_CLAIM_CODES",
]
