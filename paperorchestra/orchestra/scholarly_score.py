from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.orchestra.scoring_assessment import ScoreDimensionAssessment
from paperorchestra.orchestra.scoring_public import _public_blocking_reason
from paperorchestra.orchestra.scoring_schema import REJECTED_SCORE_DIMENSIONS, SCORE_DIMENSIONS


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
