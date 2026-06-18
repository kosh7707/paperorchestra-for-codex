from __future__ import annotations

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
