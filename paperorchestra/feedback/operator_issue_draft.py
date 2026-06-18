from __future__ import annotations

from typing import Any

from paperorchestra.feedback.candidate_approval import candidate_approval_issues_for_role
from paperorchestra.feedback.operator_answer_metadata import OPERATOR_FEEDBACK_INTENTS
from paperorchestra.feedback.operator_issue_contract import (
    ACTIONABLE_FAILURE_OWNER_CATEGORIES,
    OPERATOR_SOURCE,
    derive_operator_issue_id,
)

_MAX_GENERATED_OPERATOR_ISSUES = 3
_OPERATOR_ISSUE_SEVERITY_RANK = {
    "blocker": 0,
    "critical": 0,
    "major": 1,
    "minor": 2,
}
_OPERATOR_ISSUE_ROLE_RANK = {
    "citation_support_review": 0,
    "figure_placement_review": 1,
    "compiled_pdf": 2,
    "quality_eval": 3,
    "citation_integrity_audit": 4,
    "qa_loop_execution": 5,
    "operator_feedback_execution": 6,
    "qa_loop_plan": 7,
}


def _infer_operator_issue_owner_category(issue: dict[str, str]) -> str:
    owner = str(issue.get("owner_category") or "").strip()
    if owner in ACTIONABLE_FAILURE_OWNER_CATEGORIES:
        return owner
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "source_artifact_role",
            "source_item_key",
            "target_section",
            "rationale",
            "suggested_action",
            "authority_class",
            "owner_category",
        )
    ).lower()
    if any(token in text for token in ("pipeline", "executor", "engine", "harness", "runtime", "apply", "import", "feedback loop")):
        return "implementation"
    if any(token in text for token in ("experiment", "benchmark", "evaluation", "result")):
        return "experiment"
    if any(token in text for token in ("proof", "theorem", "security", "bound")):
        return "proof"
    if any(token in text for token in ("citation", "bibliography", "reference", "bibtex")):
        return "bibliography"
    if any(token in text for token in ("compile", "validation", "implementation", "execution")):
        return "implementation"
    if any(token in text for token in ("figure", "layout", "pdf", "caption", "page")):
        return "layout"
    if any(token in text for token in ("evidence", "source", "artifact")):
        return "evidence"
    return "author"


def _draft_intent(draft: dict[str, Any]) -> str:
    intent = str(draft.get("intent") or draft.get("primary_intent") or "").strip()
    if not intent and isinstance(draft.get("intents"), list):
        intent = next((str(item).strip() for item in draft["intents"] if str(item or "").strip()), "")
    if not intent:
        # A ready candidate in the packet is evidence that approval is possible,
        # not authority to approve it. Missing intent must continue through a
        # bounded operator-feedback candidate.
        intent = "generate_new_operator_candidate"
    if intent not in OPERATOR_FEEDBACK_INTENTS:
        raise ValueError(f"unsupported operator feedback intent: {intent}")
    return intent


def _normalized_draft_issues(draft: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "source_artifact_role",
        "source_item_key",
        "target_section",
        "severity",
        "rationale",
        "suggested_action",
        "authority_class",
        "owner_category",
    )
    issues: list[dict[str, Any]] = []
    for raw in draft.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        issue = {key: str(raw.get(key) or "").strip() for key in fields}
        if not issue["rationale"] or not issue["suggested_action"]:
            continue
        issue["owner_category"] = _infer_operator_issue_owner_category(issue)
        issues.append(issue)
    return issues


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


def _resolve_approval_request(
    intent: str,
    issues: list[dict[str, Any]],
    approval_role: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    if intent != "approve_existing_candidate":
        return intent, issues
    if not approval_role:
        return "generate_new_operator_candidate", [_default_missing_approval_issue()]
    approval_issues = candidate_approval_issues_for_role(issues, approval_role)
    return intent, approval_issues or [_default_candidate_approval_issue(approval_role)]


def _cap_generated_issues(intent: str, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if intent != "generate_new_operator_candidate" or len(issues) <= _MAX_GENERATED_OPERATOR_ISSUES:
        return issues
    ranked = sorted(
        enumerate(issues),
        key=lambda pair: (
            _OPERATOR_ISSUE_SEVERITY_RANK.get(pair[1].get("severity", "").lower(), 3),
            _OPERATOR_ISSUE_ROLE_RANK.get(pair[1].get("source_artifact_role", ""), 9),
            pair[0],
        ),
    )
    return [issue for _index, issue in ranked[:_MAX_GENERATED_OPERATOR_ISSUES]]


def _with_operator_issue_identity(packet_sha256: str, issue: dict[str, Any]) -> dict[str, Any]:
    result = dict(issue)
    result["id"] = derive_operator_issue_id(
        packet_sha256,
        source_artifact_role=result["source_artifact_role"],
        source_item_key=result["source_item_key"],
        target_section=result["target_section"],
        rationale=result["rationale"],
        suggested_action=result["suggested_action"],
    )
    result["source"] = OPERATOR_SOURCE
    result["not_independent_human_review"] = True
    return result


def normalize_operator_issue_draft(
    *,
    packet_sha256: str,
    draft: dict[str, Any],
    approval_role: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    intent = _draft_intent(draft)
    issues = _normalized_draft_issues(draft)
    intent, issues = _resolve_approval_request(intent, issues, approval_role)
    issues = _cap_generated_issues(intent, issues) or [_fallback_human_needed_issue()]
    return intent, [_with_operator_issue_identity(packet_sha256, issue) for issue in issues]
