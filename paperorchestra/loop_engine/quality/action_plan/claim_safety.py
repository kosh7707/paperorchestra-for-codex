from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action
from paperorchestra.loop_engine.quality.action_plan.citation_integrity import _append_citation_integrity_actions
from paperorchestra.loop_engine.quality.action_plan.citation_quality import _append_citation_quality_actions
from paperorchestra.loop_engine.quality.action_plan.citation_support import _append_citation_support_actions
from paperorchestra.loop_engine.quality.action_plan.figure_grounding import _append_figure_grounding_actions
from paperorchestra.loop_engine.quality.action_plan.source_material import (
    _append_source_material_fidelity_actions,
    _append_source_obligation_actions,
)


def _append_tier2_claim_safety_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    if not isinstance(tier2, dict):
        return
    checks = tier2.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
    _append_figure_grounding_actions(actions, checks.get("figure_grounding"))
    _append_citation_support_actions(actions, checks.get("citation_support_critic"))
    _append_citation_quality_actions(actions, checks.get("citation_quality_gate"))
    _append_citation_integrity_actions(actions, checks.get("citation_integrity_gate"))
    _append_source_material_fidelity_actions(actions, checks.get("source_material_fidelity"))
    _append_source_obligation_actions(actions, checks.get("source_obligations"))
    _append_high_risk_claim_actions(actions, checks.get("high_risk_claim_sweep"))
    _append_planning_satisfaction_actions(actions, checks.get("planning_satisfaction"))


def _append_high_risk_claim_actions(actions: list[dict[str, Any]], high_risk_check: Any) -> None:
    if isinstance(high_risk_check, dict) and high_risk_check.get("status") == "fail":
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
    if isinstance(planning_check, dict) and planning_check.get("status") == "fail":
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
