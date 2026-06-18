from __future__ import annotations

OPERATOR_FEEDBACK_INTENTS = {
    "approve_existing_candidate",
    "generate_new_operator_candidate",
    "reject_candidate_with_reason",
}

HUMAN_NEEDED_METADATA_SCHEMA_VERSION = "human-needed-answer-metadata/1"
HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION = "human-needed-answer-public/1"
HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS = {
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
    HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION,
}
HUMAN_NEEDED_METADATA_FORBIDDEN_KEYS = {
    "answer_text",
    "private_answer_path",
    "private_path",
    "raw",
    "raw_answer",
}
HUMAN_NEEDED_HANDOFF_TYPES = {
    "candidate_approval",
    "citation_author_judgment",
    "figure_grounding_decision",
    "environment_dependency",
    "reviewer_independence",
    "no_progress_escalation",
    "unsupported_handler",
    "planning_satisfaction",
    "general_operator_feedback",
}
HUMAN_NEEDED_METADATA_ALLOWED_KEYS = {
    "schema_version",
    "session_id",
    "packet_sha256",
    "packet_file_sha256",
    "manuscript_sha256",
    "answer_sha256",
    "private_answer_artifact_sha256",
    "decision_kind",
    "handoff_type",
    "target_action_id",
    "target_issue_ids",
    "selected_handoff_source",
    "answer",
}
HUMAN_NEEDED_SELECTED_SOURCE_ALLOWED_KEYS = {"role", "sha256"}
