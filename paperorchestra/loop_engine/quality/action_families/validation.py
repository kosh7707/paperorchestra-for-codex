from __future__ import annotations

import shlex
from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.policy import AUTO_REPAIR_CODES, SEMI_AUTO_REPAIR_CODES
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists


def _automation_for_issue(code: str) -> str:
    if code in SEMI_AUTO_REPAIR_CODES:
        return "semi_auto"
    if code in AUTO_REPAIR_CODES:
        return "automatic"
    return "human_needed"


def _target_section_from_stage(stage: str | None) -> str | None:
    if stage == "intro_related":
        return "Introduction, Related Work"
    if stage == "section_writing":
        return "full manuscript"
    if stage == "refinement":
        return "current manuscript"
    return None


def _section_arg(target: str | None) -> str:
    if not target or target in {"full manuscript", "current manuscript"}:
        return ""
    return f" --only-sections {shlex.quote(target)}"


def _commands_for_validation_issue(code: str, target: str | None) -> list[str]:
    section_arg = _section_arg(target)
    if code == "unsupported_comparative_claim":
        return [
            "paperorchestra quality-gate --no-fail-on-block",
            "paperorchestra critique",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
            "paperorchestra qa-loop --quality-mode claim_safe",
        ]
    if code in {"unknown_citation_keys", "citation_coverage_insufficient"}:
        return [
            "paperorchestra run --provider shell --discovery-mode search-grounded",
            "paperorchestra critique",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code == "numeric_grounding_mismatch":
        return [
            "paperorchestra quality-gate --no-fail-on-block",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code in {"expected_section_missing", "expected_section_too_shallow"}:
        return [
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra critique",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code == "plot_plan_not_reflected":
        return [
            "paperorchestra run --provider shell",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra critique",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    return ["paperorchestra quality-gate --no-fail-on-block"]


def _claim_safety_approval(code: str) -> tuple[str | None, str | None]:
    if code == "unsupported_comparative_claim":
        return (
            "Softening or deleting a comparative claim changes substantive paper content; a citation-support critic or human must approve before committing it.",
            "citation_support_critic",
        )
    if code == "numeric_grounding_mismatch":
        return (
            "Changing numeric prose can alter empirical claims; the rewrite must be checked against the experimental log.",
            "claim_safety_critic",
        )
    if code == "citation_coverage_insufficient":
        return (
            "Adding citation coverage is only safe from the verified pool; new citations must follow discovery -> verification -> registry.",
            "citation_support_critic",
        )
    return (None, None)


def _validation_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for report in reproducibility.get("validation_warning_reports") or []:
        source = report.get("path")
        payload = _read_json_if_exists(source)
        if not isinstance(payload, dict):
            continue
        stage = payload.get("stage")
        target = _target_section_from_stage(stage)
        for issue in payload.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "unknown_validation_issue")
            severity = str(issue.get("severity") or "warning")
            if severity not in {"warning", "error"}:
                continue
            key = (code, stage if isinstance(stage, str) else None, source if isinstance(source, str) else None)
            if key in seen:
                continue
            seen.add(key)
            automation = _automation_for_issue(code)
            why, approval = _claim_safety_approval(code)
            actions.append(
                _action(
                    action_id=f"validation:{len(actions)+1}",
                    code=code,
                    source=source,
                    target=target,
                    automation=automation,
                    reason=str(issue.get("message") or f"Validation issue {code}"),
                    suggested_commands=_commands_for_validation_issue(code, target),
                    ralph_instruction=(
                        "Produce a candidate rewrite only from existing evidence; do not add new facts or citations outside the verified registry."
                        if automation == "semi_auto"
                        else "Rewrite only the affected section when possible; preserve validated citations, numbers, labels, and prior accepted structure."
                        if automation == "automatic"
                        else "Escalate this validation issue to a human reviewer before changing manuscript content."
                    ),
                    why_not_automatic=why,
                    approval_required_from=approval,
                )
            )
    return actions


def _strict_content_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "strict_content_gate")
        source = issue.get("source") if isinstance(issue.get("source"), str) else None
        key = (code, source)
        if key in seen:
            continue
        seen.add(key)
        kind = issue.get("kind")
        why = None
        approval = None
        if code in {"validation_report_missing", "validation_report_stale"}:
            automation = "automatic"
            commands = [
                "paperorchestra quality-gate --no-fail-on-block",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ]
            instruction = (
                "Regenerate a validation report for the current manuscript before attempting content repair; do not act on stale validation warnings."
            )
        elif code in {"figure_placement_review_missing", "figure_placement_review_stale"}:
            automation = "automatic"
            commands = [
                "paperorchestra critique",
                "paperorchestra quality-gate --no-fail-on-block",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ]
            instruction = (
                "Regenerate figure-placement review for the current manuscript before moving figures or rewriting figure references."
            )
        elif kind in {"figure_placement_warning", "figure_placement_failure"}:
            automation = "human_needed"
            commands = [
                "paperorchestra critique",
                "paperorchestra write-sections --only-sections \"Implementation Results\"",
                "paperorchestra quality-gate --no-fail-on-block",
            ]
            instruction = (
                "Prepare a targeted figure-grounding decision for a human reviewer; do not auto-edit figure placement, captions, or visual evidence from the quality loop."
            )
            why = "Figure placement/caption changes affect narrative flow, visual evidence, and claim meaning; PaperOrchestra can flag them but cannot safely auto-commit final placement."
            approval = "figure_placement_review_critic"
        else:
            automation = _automation_for_issue(code)
            commands = _commands_for_validation_issue(code, None)
            instruction = (
                "Produce a candidate claim-safe rewrite grounded only in existing logs/citations; require second-critic approval before commit."
                if automation == "semi_auto"
                else "Rewrite the affected structural issue without adding new claims."
                if automation == "automatic"
                else "Escalate this strict content issue to a human reviewer."
            )
            why, approval = _claim_safety_approval(code)
        actions.append(
            _action(
                action_id=f"strict-content:{len(actions)+1}",
                code=code,
                source=source,
                target=issue.get("stage") if isinstance(issue.get("stage"), str) else None,
                automation=automation,
                reason=str(issue.get("message") or f"Strict content gate issue {code}"),
                suggested_commands=commands,
                ralph_instruction=instruction,
                why_not_automatic=why,
                approval_required_from=approval,
            )
        )
    return actions
