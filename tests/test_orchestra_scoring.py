from __future__ import annotations

import json
import unittest

from paperorchestra.orchestra_scoring import ScholarlyScore, ScoringBundleBuilder


class OrchestraScoringTests(unittest.TestCase):
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
