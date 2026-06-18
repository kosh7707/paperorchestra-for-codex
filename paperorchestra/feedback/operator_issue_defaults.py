from __future__ import annotations


def _default_missing_approval_issue() -> dict[str, str]:
    return {
        "source_artifact_role": "qa_loop_execution",
        "source_item_key": "candidate_progress_without_candidate_approval",
        "target_section": "Whole manuscript",
        "severity": "major",
        "rationale": (
            "The operator requested approve_existing_candidate, but the packet has no actionable candidate_approval artifact; "
            "forward-progress diagnostics alone are not approval authority."
        ),
        "suggested_action": (
            "Generate a new operator-feedback candidate from the current manuscript and the residual claim-safety issues instead of "
            "approving a non-ready candidate."
        ),
        "authority_class": "author_feedback",
        "owner_category": "author",
    }


def _default_candidate_approval_issue(approval_role: str) -> dict[str, str]:
    return {
        "source_artifact_role": approval_role,
        "source_item_key": "candidate_approval",
        "target_section": "Whole manuscript",
        "severity": "major",
        "rationale": "The packet exposes a forward-progress candidate approval artifact for supervised continuation.",
        "suggested_action": (
            "Approve the ready candidate so the next loop iteration can continue from the improved manuscript while preserving "
            "claim-safety gates."
        ),
        "authority_class": "author_feedback",
        "owner_category": "author",
    }


def _fallback_human_needed_issue() -> dict[str, str]:
    return {
        "source_artifact_role": "qa_loop_plan",
        "source_item_key": "verdict:human_needed",
        "target_section": "Whole manuscript",
        "severity": "major",
        "rationale": "QA loop reached human_needed and needs bounded operator feedback.",
        "suggested_action": (
            "Improve narrative coherence and claim-safety presentation while preserving paper-specific claims from the source packet only."
        ),
        "authority_class": "author_feedback",
        "owner_category": "author",
    }
