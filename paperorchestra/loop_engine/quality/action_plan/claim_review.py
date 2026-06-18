from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action


def _append_high_risk_claim_actions(actions: list[dict[str, Any]], high_risk_check: Any) -> None:
    if not (isinstance(high_risk_check, dict) and high_risk_check.get("status") == "fail"):
        return

    actions.append(
        _action(
            action_id="quality-eval:high-risk-claim-sweep",
            code="high_risk_uncited_claim",
            source=None,
            target="claim safety",
            automation="semi_auto",
            reason="High-risk uncited factual, novelty, security, benchmark, or numeric claims remain without citation, source-obligation support, or limitation scoping.",
            suggested_commands=[
                "paperorchestra qa-loop-step",
                "paperorchestra critique --citation-evidence-mode web",
                "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ],
            ralph_instruction="Ground each high-risk uncited claim with existing verified evidence, scope it as a limitation/author-material claim, or delete it; do not add new claims or bibliography keys.",
            why_not_automatic="Repairing high-risk claims can alter factual substance; the candidate must be checked by claim-safety/citation critics before promotion.",
            approval_required_from="claim_safety_critic",
        )
    )


def _append_planning_satisfaction_actions(actions: list[dict[str, Any]], planning_check: Any) -> None:
    if not (isinstance(planning_check, dict) and planning_check.get("status") == "fail"):
        return

    actions.append(
        _action(
            action_id="quality-eval:planning-satisfaction",
            code="planning_satisfaction_failed",
            source=None,
            target="narrative/claim/citation plan satisfaction",
            automation="human_needed",
            reason="The manuscript does not satisfy current narrative, claim-map, or citation-placement obligations.",
            suggested_commands=["paperorchestra write-sections", "paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
            ralph_instruction="Plan satisfaction failures are substantive writing issues; implement a supported targeted rewrite handler before continuing automatically.",
            why_not_automatic="Naive automated rewriting can satisfy keyword gates dishonestly; requires a dedicated handler and critic approval.",
            approval_required_from="plan_satisfaction_critic",
        )
    )
