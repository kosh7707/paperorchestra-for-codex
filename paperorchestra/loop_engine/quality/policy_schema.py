from __future__ import annotations

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

__all__ = [
    "BUDGET_CONSUMING_HISTORY_EVENTS",
    "CITATION_SUPPORT_STATUSES",
    "DEFAULT_MAX_ITERATIONS",
    "HISTORY_FILENAME",
    "QUALITY_EVAL_SCHEMA_VERSION",
    "QUALITY_MODES",
    "QA_LOOP_PLAN_SCHEMA_VERSION",
]
