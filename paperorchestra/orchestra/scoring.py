from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.orchestra.scholarly_score import ScholarlyScore
from paperorchestra.orchestra.scoring_assessment import ScoreDimensionAssessment
from paperorchestra.orchestra.scoring_public import _public_blocking_reason
from paperorchestra.orchestra.scoring_schema import CONFIDENCE_LEVELS, REJECTED_SCORE_DIMENSIONS, SCORE_DIMENSIONS

__all__ = [
    "CONFIDENCE_LEVELS",
    "REJECTED_SCORE_DIMENSIONS",
    "SCORE_DIMENSIONS",
    "ScholarlyScore",
    "ScoreDimensionAssessment",
    "ScoringBundleBuilder",
    "ScoringInputBundle",
    "_public_blocking_reason",
    "render_compact_scorecard",
]


@dataclass(frozen=True)
class ScoringInputBundle:
    schema_version: str
    phase: str
    manuscript_sha256: str
    required_artifacts: dict[str, str]
    compressed_evidence: dict[str, Any]
    complete: bool
    blocking_reasons: list[str] = field(default_factory=list)
    private_raw_text: str | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "manuscript_sha256": self.manuscript_sha256,
            "required_artifacts": dict(self.required_artifacts),
            "compressed_evidence": dict(self.compressed_evidence),
            "complete": self.complete,
            "blocking_reasons": [_public_blocking_reason(reason) for reason in self.blocking_reasons],
            "private_safe": True,
        }


class ScoringBundleBuilder:
    def build(
        self,
        *,
        phase: str,
        manuscript_sha256: str,
        required_artifacts: dict[str, str],
        compressed_evidence: dict[str, Any],
        private_raw_text: str | None = None,
    ) -> ScoringInputBundle:
        blockers: list[str] = []
        if len(manuscript_sha256) != 64:
            blockers.append("invalid_manuscript_sha256")
        for name, ref in required_artifacts.items():
            if not ref:
                blockers.append(f"missing_required_artifact:{name}")
        return ScoringInputBundle(
            schema_version="scholarly-score-input-bundle/1",
            phase=phase,
            manuscript_sha256=manuscript_sha256,
            required_artifacts=dict(required_artifacts),
            compressed_evidence=dict(compressed_evidence),
            complete=not blockers,
            blocking_reasons=blockers,
            private_raw_text=private_raw_text,
        )


def render_compact_scorecard(score: ScholarlyScore, *, blockers: list[str] | None = None) -> str:
    summary = score.to_summary()
    blockers = list(blockers or summary["blocking_reasons"])
    lines = [
        f"Paper readiness score: {score.overall:.0f}/100 — {score.readiness_band}",
        "",
        "Weakest dimensions:",
    ]
    weakest = summary["weakest_dimensions"]
    if weakest:
        for item in weakest:
            lines.append(f"- {item['dimension']}: {item['score']:.0f}")
    else:
        lines.append("- unavailable: full scorecard dimensions missing")
    lines.extend(["", "Current blockers:"])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none recorded")
    lines.extend(
        [
            "",
            "Next:",
            "- Use the weakest dimensions and blockers to prioritize repair.",
            "- Hard gates still override this scorecard.",
        ]
    )
    return "\n".join(lines)
