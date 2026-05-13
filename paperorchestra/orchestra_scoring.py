from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCORE_DIMENSIONS = (
    "claim_validity",
    "evidence_claim_calibration",
    "source_grounding",
    "citation_integrity",
    "contribution_and_novelty",
    "experimental_interpretation",
    "scope_and_limitations",
    "argument_structure",
    "technical_specificity",
    "prose_and_terminology",
    "reproducibility_surface",
)
REJECTED_SCORE_DIMENSIONS = {"reviewer_attack_surface"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}


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


@dataclass
class ScoreDimensionAssessment:
    score: float
    confidence: str
    rationale: str
    evidence_links: list[str] = field(default_factory=list)
    top_penalties: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    private_detail: str | None = field(default=None, repr=False)

    def validation_errors(self, dimension: str) -> list[str]:
        errors: list[str] = []
        if not 0 <= self.score <= 100:
            errors.append(f"score_dimension_out_of_range:{dimension}")
        if self.confidence not in CONFIDENCE_LEVELS:
            errors.append(f"score_dimension_invalid_confidence:{dimension}")
        if not self.evidence_links:
            errors.append(f"score_dimension_missing_evidence_links:{dimension}")
        return errors

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence_links": list(self.evidence_links),
            "top_penalties": list(self.top_penalties),
            "recommended_actions": list(self.recommended_actions),
        }


@dataclass
class ScholarlyScore:
    overall: float
    readiness_band: str
    evidence_links: list[str] = field(default_factory=list)
    dimensions: dict[str, ScoreDimensionAssessment] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    private_rationale: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.evidence_links and "missing_evidence_links" not in self.blocking_reasons:
            self.blocking_reasons.append("missing_evidence_links")
        if not 0 <= self.overall <= 100 and "overall_score_out_of_range" not in self.blocking_reasons:
            self.blocking_reasons.append("overall_score_out_of_range")
        for dimension in sorted(set(self.dimensions) & REJECTED_SCORE_DIMENSIONS):
            reason = f"rejected_score_dimension:{dimension}"
            if reason not in self.blocking_reasons:
                self.blocking_reasons.append(reason)
        accepted = set(SCORE_DIMENSIONS)
        for dimension in sorted(set(self.dimensions) - accepted - REJECTED_SCORE_DIMENSIONS):
            reason = f"unknown_score_dimension:{dimension}"
            if reason not in self.blocking_reasons:
                self.blocking_reasons.append(reason)
        for dimension in SCORE_DIMENSIONS:
            assessment = self.dimensions.get(dimension)
            if assessment is None:
                reason = f"missing_score_dimension:{dimension}"
                if reason not in self.blocking_reasons:
                    self.blocking_reasons.append(reason)
                continue
            for reason in assessment.validation_errors(dimension):
                if reason not in self.blocking_reasons:
                    self.blocking_reasons.append(reason)

    @property
    def valid(self) -> bool:
        return not self.blocking_reasons

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "scholarly-score/1",
            "overall": self.overall,
            "readiness_band": self.readiness_band,
            "evidence_links": list(self.evidence_links),
            "dimensions": {
                dimension: self.dimensions[dimension].to_public_dict()
                for dimension in SCORE_DIMENSIONS
                if dimension in self.dimensions
            },
            "blocking_reasons": [_public_blocking_reason(reason) for reason in self.blocking_reasons],
            "valid": self.valid,
            "private_safe": True,
        }

    def to_summary(self) -> dict[str, Any]:
        weakest = sorted(
            (
                {"dimension": dimension, "score": assessment.score}
                for dimension, assessment in self.dimensions.items()
                if dimension in SCORE_DIMENSIONS
            ),
            key=lambda item: item["score"],
        )[:3]
        return {
            "overall": self.overall,
            "readiness_band": self.readiness_band,
            "valid": self.valid,
            "weakest_dimensions": weakest,
            "blocking_reasons": [_public_blocking_reason(reason) for reason in self.blocking_reasons],
        }


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


def _public_blocking_reason(reason: str) -> str:
    if reason.startswith("unknown_score_dimension:"):
        return "unknown_score_dimension:<redacted>"
    return reason
