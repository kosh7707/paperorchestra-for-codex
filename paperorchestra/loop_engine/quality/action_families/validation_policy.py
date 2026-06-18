from __future__ import annotations

import shlex

from paperorchestra.loop_engine.quality.policy import AUTO_REPAIR_CODES, SEMI_AUTO_REPAIR_CODES


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
    return None, None
