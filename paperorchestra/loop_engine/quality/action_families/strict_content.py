from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.action_families.validation_policy import (
    _automation_for_issue,
    _claim_safety_approval,
    _commands_for_validation_issue,
)


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
        commands, instruction, automation, why, approval = _strict_issue_response(code, issue)
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


def _strict_issue_response(code: str, issue: dict[str, Any]) -> tuple[list[str], str, str, str | None, str | None]:
    kind = issue.get("kind")
    if code in {"validation_report_missing", "validation_report_stale"}:
        return (
            ["paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
            "Regenerate a validation report for the current manuscript before attempting content repair; do not act on stale validation warnings.",
            "automatic",
            None,
            None,
        )
    if code in {"figure_placement_review_missing", "figure_placement_review_stale"}:
        return (
            ["paperorchestra critique", "paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
            "Regenerate figure-placement review for the current manuscript before moving figures or rewriting figure references.",
            "automatic",
            None,
            None,
        )
    if code in {"page_layout_review_missing", "page_layout_review_stale"}:
        return (
            ["paperorchestra visual-audit", "paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
            "Regenerate rendered-page visual review for the compiled manuscript before accepting page layout or visual artifacts.",
            "automatic",
            None,
            None,
        )
    if code in {"page_layout_render_failed", "page_layout_render_unavailable"}:
        return (
            ["paperorchestra visual-audit", "paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
            "Restore rendered-page evidence for the current compiled PDF; do not collapse render failure into a missing review or visual pass.",
            "automatic",
            None,
            None,
        )
    if kind in {"page_layout_warning", "page_layout_failure"}:
        return (
            [
                "paperorchestra visual-audit --findings-json page-visual-findings.json",
                "paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1",
                "paperorchestra quality-gate --no-fail-on-block",
            ],
            "Create a visual repair brief and route machine-actionable layout fixes back into PaperOrchestra/Critic before human handoff.",
            "semi_auto",
            "Rendered PDF visual findings require page-image evidence and a repair brief; do not silently convert them into TeX-only approval.",
            "visual_layout_critic",
        )
    if code == "visual_final_artwork_handoff" or kind == "page_layout_human":
        return (
            [
                "Replace draft/generated artwork with human-authored final artwork or provide an explicit visual design decision.",
                "paperorchestra visual-audit --findings-json page-visual-findings.json",
                "paperorchestra quality-gate --no-fail-on-block",
            ],
            "Stop before pretending draft artwork or a disputed visual is final; prepare exact author-owned visual decisions/artifacts.",
            "human_needed",
            "Final artwork, semantic visual evidence disputes, and aesthetic preferences are human-owned publication decisions.",
            "author_visual_owner",
        )
    if kind in {"figure_placement_warning", "figure_placement_failure"}:
        return (
            [
                "paperorchestra critique",
                "paperorchestra write-sections --only-sections \"Implementation Results\"",
                "paperorchestra quality-gate --no-fail-on-block",
            ],
            "Prepare a targeted figure-grounding decision for a human reviewer; do not auto-edit figure placement, captions, or visual evidence from the quality loop.",
            "human_needed",
            "Figure placement/caption changes affect narrative flow, visual evidence, and claim meaning; PaperOrchestra can flag them but cannot safely auto-commit final placement.",
            "figure_placement_review_critic",
        )
    automation = _automation_for_issue(code)
    why, approval = _claim_safety_approval(code)
    return (
        _commands_for_validation_issue(code, None),
        "Produce a candidate claim-safe rewrite grounded only in existing logs/citations; require second-critic approval before commit."
        if automation == "semi_auto"
        else "Rewrite the affected structural issue without adding new claims."
        if automation == "automatic"
        else "Escalate this strict content issue to a human reviewer.",
        automation,
        why,
        approval,
    )
