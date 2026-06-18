from __future__ import annotations

OPERATOR_PACKET_SCHEMA_VERSION = "operator-review-packet/1"
OPERATOR_FEEDBACK_SCHEMA_VERSION = "operator-feedback/1"
OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION = "operator-feedback-import/1"
OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION = "operator-feedback-execution/1"
OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION = "operator-feedback-incorporation/1"
OPERATOR_PUBLIC_ENTRYPOINTS = {
    "build-operator-review-packet",
    "import-operator-feedback",
    "apply-operator-feedback",
}
OVERALL_CATASTROPHIC_DROP = 8.0
AXIS_CATASTROPHIC_DROP = 15.0
HUMAN_REVIEWABLE_NEW_TIER2_CODES = {
    "citation_support_manual_check",
}
OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES = {
    "citation_duplicate_support",
    "citation_integrity_failed",
    "citation_integrity_audit_fail",
    "citation_support_weak",
    "citation_support_manual_check",
    "citation_support_unsupported",
    "citation_support_contradicted",
    "citation_support_metadata_only",
    "citation_support_insufficient_evidence",
    "citation_support_evidence_missing",
    "high_risk_uncited_claim",
}
