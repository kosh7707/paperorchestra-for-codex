from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from paperorchestra.loop_engine.quality.eval_tiers import _status_from_failures, _strict_issue_codes, _tier


@dataclass(frozen=True)
class PreconditionContext:
    paper_full_tex: str | None
    paper_exists: bool
    manuscript_hash: str | None
    reproducibility: Mapping[str, Any]
    planning_status: Mapping[str, Any]


@dataclass(frozen=True)
class PreconditionTierResult:
    tier: dict[str, Any]
    artifact_checks: dict[str, Any]
    planning_freshness_codes: list[str]


class PreconditionTierBuilder:
    """Build Tier 0 quality-eval checks for artifact presence and freshness."""

    freshness_issue_kinds = {
        "validation_report_missing",
        "validation_report_stale",
        "figure_placement_review_missing",
        "figure_placement_review_stale",
        "page_layout_review_missing",
        "page_layout_review_stale",
    }

    def build(self, context: PreconditionContext) -> PreconditionTierResult:
        failing_codes: list[str] = []
        artifact_checks: dict[str, Any] = {}

        artifact_checks["paper_full_tex"] = {
            "status": "pass" if context.paper_exists else "fail",
            "path": context.paper_full_tex,
        }
        if not context.paper_exists:
            failing_codes.append("paper_full_tex_missing")

        artifact_checks["manuscript_hash"] = {
            "status": "pass" if context.manuscript_hash else "fail",
            "sha256": context.manuscript_hash,
        }
        if not context.manuscript_hash:
            failing_codes.append("manuscript_hash_missing")

        stale_or_missing = _strict_issue_codes(
            dict(context.reproducibility),
            kinds=self.freshness_issue_kinds,
        )
        planning_freshness_codes = list(context.planning_status.get("failing_codes") or [])

        artifact_checks["freshness"] = {
            "status": "pass" if not (stale_or_missing or planning_freshness_codes) else "fail",
            "stale_against_manuscript_hash": stale_or_missing,
            "planning_artifact_issues": planning_freshness_codes,
        }

        failing_codes.extend(stale_or_missing)
        if context.paper_exists:
            failing_codes.extend(planning_freshness_codes)

        tier = _tier(
            status=_status_from_failures(failing_codes),
            checks={
                "artifacts_present": artifact_checks["paper_full_tex"],
                "manuscript_hash": artifact_checks["manuscript_hash"],
                "freshness": artifact_checks["freshness"],
                "planning_artifacts": {
                    "status": context.planning_status.get("status"),
                    "failing_codes": planning_freshness_codes,
                    "artifacts": context.planning_status.get("artifacts"),
                },
            },
            failing_codes=failing_codes,
        )

        return PreconditionTierResult(
            tier=tier,
            artifact_checks=artifact_checks,
            planning_freshness_codes=planning_freshness_codes,
        )


def build_precondition_tier(context: PreconditionContext) -> PreconditionTierResult:
    return PreconditionTierBuilder().build(context)
