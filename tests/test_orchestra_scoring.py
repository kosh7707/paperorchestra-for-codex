from __future__ import annotations

import json
import unittest

from paperorchestra.orchestra_scoring import (
    SCORE_DIMENSIONS,
    ScoreDimensionAssessment,
    ScholarlyScore,
    ScoringBundleBuilder,
    render_compact_scorecard,
)


def _complete_dimensions(score: float = 80.0) -> dict[str, ScoreDimensionAssessment]:
    return {
        dimension: ScoreDimensionAssessment(
            score=score,
            confidence="medium",
            rationale=f"{dimension} rationale",
            evidence_links=[f"evidence/{dimension}.json"],
            top_penalties=[],
            recommended_actions=[f"improve_{dimension}"],
        )
        for dimension in SCORE_DIMENSIONS
    }


class OrchestraScoringTests(unittest.TestCase):
    def test_rubric_has_general_dimensions_and_excludes_reviewer_attack_surface(self) -> None:
        self.assertEqual(
            SCORE_DIMENSIONS,
            (
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
            ),
        )
        self.assertNotIn("reviewer_attack_surface", SCORE_DIMENSIONS)

    def test_scoring_bundle_binds_to_manuscript_hash_and_required_artifact_refs(self) -> None:
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "artifacts/paper.full.tex", "citations": "artifacts/citation-review.json"},
            compressed_evidence={"summary": "synthetic evidence summary"},
        )
        self.assertEqual(bundle.manuscript_sha256, "a" * 64)
        self.assertEqual(bundle.required_artifacts["paper"], "artifacts/paper.full.tex")
        self.assertTrue(bundle.complete)

    def test_missing_required_scoring_artifact_blocks_score_generation(self) -> None:
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": ""},
            compressed_evidence={},
        )
        self.assertFalse(bundle.complete)
        self.assertIn("missing_required_artifact:paper", bundle.blocking_reasons)

    def test_critic_score_without_evidence_links_is_rejected(self) -> None:
        score = ScholarlyScore(overall=88.0, readiness_band="near_ready", evidence_links=[])
        self.assertFalse(score.valid)
        self.assertIn("missing_evidence_links", score.blocking_reasons)

    def test_complete_scholarly_scorecard_exports_public_dimensions(self) -> None:
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=_complete_dimensions(),
        )
        payload = score.to_public_dict()

        self.assertTrue(score.valid)
        self.assertEqual(set(payload["dimensions"]), set(SCORE_DIMENSIONS))
        self.assertEqual(payload["dimensions"]["claim_validity"]["confidence"], "medium")
        self.assertIn("weakest_dimensions", score.to_summary())

    def test_missing_score_dimension_invalidates_scorecard(self) -> None:
        dimensions = _complete_dimensions()
        dimensions.pop("source_grounding")
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        self.assertFalse(score.valid)
        self.assertIn("missing_score_dimension:source_grounding", score.blocking_reasons)

    def test_dimension_without_evidence_links_invalidates_scorecard(self) -> None:
        dimensions = _complete_dimensions()
        dimensions["claim_validity"] = ScoreDimensionAssessment(
            score=80.0,
            confidence="medium",
            rationale="unsupported rationale",
            evidence_links=[],
        )
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        self.assertFalse(score.valid)
        self.assertIn("score_dimension_missing_evidence_links:claim_validity", score.blocking_reasons)

    def test_invalid_dimension_confidence_and_score_are_rejected(self) -> None:
        dimensions = _complete_dimensions()
        dimensions["claim_validity"] = ScoreDimensionAssessment(
            score=101.0,
            confidence="certain",
            rationale="invalid",
            evidence_links=["score-input.json"],
        )
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        self.assertFalse(score.valid)
        self.assertIn("score_dimension_out_of_range:claim_validity", score.blocking_reasons)
        self.assertIn("score_dimension_invalid_confidence:claim_validity", score.blocking_reasons)

    def test_reviewer_attack_surface_dimension_is_rejected(self) -> None:
        dimensions = _complete_dimensions()
        dimensions["reviewer_attack_surface"] = ScoreDimensionAssessment(
            score=90.0,
            confidence="low",
            rationale="wrong dimension",
            evidence_links=["score-input.json"],
        )
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        self.assertFalse(score.valid)
        self.assertIn("rejected_score_dimension:reviewer_attack_surface", score.blocking_reasons)

    def test_unknown_extra_dimension_is_invalid_and_not_publicly_exported(self) -> None:
        dimensions = _complete_dimensions()
        dimensions["domain_specific_private_dimension"] = ScoreDimensionAssessment(
            score=90.0,
            confidence="medium",
            rationale="PRIVATE_DOMAIN_SPECIFIC_RATIONALE_SHOULD_NOT_EXPORT",
            evidence_links=["score-input.json"],
        )
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        rendered = json.dumps(score.to_public_dict(), ensure_ascii=False)
        summary_rendered = json.dumps(score.to_summary(), ensure_ascii=False)
        compact = render_compact_scorecard(score)
        self.assertFalse(score.valid)
        self.assertIn("unknown_score_dimension:domain_specific_private_dimension", score.blocking_reasons)
        self.assertNotIn("domain_specific_private_dimension", rendered)
        self.assertNotIn("PRIVATE_DOMAIN_SPECIFIC_RATIONALE_SHOULD_NOT_EXPORT", rendered)
        self.assertNotIn("domain_specific_private_dimension", summary_rendered)
        self.assertNotIn("domain_specific_private_dimension", compact)
        self.assertNotIn("PRIVATE_DOMAIN_SPECIFIC_RATIONALE_SHOULD_NOT_EXPORT", compact)

    def test_public_safe_scoring_bundle_omits_private_raw_text(self) -> None:
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "artifacts/paper.full.tex"},
            compressed_evidence={"summary": "safe synthetic summary"},
            private_raw_text="PRIVATE_RAW_TEXT_SHOULD_NOT_LEAK",
        )
        rendered = json.dumps(bundle.to_public_dict(), ensure_ascii=False)
        self.assertNotIn("PRIVATE_RAW_TEXT_SHOULD_NOT_LEAK", rendered)

    def test_public_safe_scorecard_omits_private_dimension_detail(self) -> None:
        dimensions = _complete_dimensions()
        dimensions["claim_validity"] = ScoreDimensionAssessment(
            score=80.0,
            confidence="medium",
            rationale="public rationale",
            evidence_links=["score-input.json"],
            private_detail="PRIVATE_SCORE_DETAIL_SHOULD_NOT_LEAK",
        )
        score = ScholarlyScore(
            overall=82.0,
            readiness_band="near_ready",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
        )
        rendered = json.dumps(score.to_public_dict(), ensure_ascii=False)
        self.assertNotIn("PRIVATE_SCORE_DETAIL_SHOULD_NOT_LEAK", rendered)

    def test_compact_scorecard_shows_score_blockers_and_next_step(self) -> None:
        dimensions = _complete_dimensions(score=75.0)
        dimensions["source_grounding"] = ScoreDimensionAssessment(
            score=42.0,
            confidence="medium",
            rationale="needs stronger sources",
            evidence_links=["source-audit.json"],
            top_penalties=["missing primary source"],
            recommended_actions=["search stronger sources"],
        )
        score = ScholarlyScore(
            overall=58.0,
            readiness_band="promising_but_blocked",
            evidence_links=["score-input.json"],
            dimensions=dimensions,
            blocking_reasons=["unsupported_critical_claim"],
        )
        text = render_compact_scorecard(score, blockers=["unsupported_critical_claim"])
        self.assertIn("Paper readiness score: 58/100", text)
        self.assertIn("source_grounding: 42", text)
        self.assertIn("unsupported_critical_claim", text)
        self.assertIn("Next:", text)
