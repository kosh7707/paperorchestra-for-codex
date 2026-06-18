from __future__ import annotations

from typing import Any

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
