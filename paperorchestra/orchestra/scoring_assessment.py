from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.orchestra.scoring_schema import CONFIDENCE_LEVELS


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
