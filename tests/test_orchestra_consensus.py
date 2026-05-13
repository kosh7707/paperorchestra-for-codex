from __future__ import annotations

import json
import unittest

from paperorchestra.orchestra_consensus import ConsensusPolicy, CriticVerdict


class OrchestraConsensusTests(unittest.TestCase):
    def test_two_agreeing_critic_verdicts_produce_near_ready_consensus(self) -> None:
        consensus = ConsensusPolicy().evaluate(
            [
                CriticVerdict(critic_id="A", verdict="near_ready", evidence_links=["score.json"]),
                CriticVerdict(critic_id="B", verdict="near_ready", evidence_links=["score.json"]),
            ]
        )
        self.assertEqual(consensus.status, "pass")
        self.assertEqual(consensus.readiness_band, "near_ready")

    def test_two_disagreeing_critic_verdicts_plan_third_adjudication(self) -> None:
        consensus = ConsensusPolicy().evaluate(
            [
                CriticVerdict(critic_id="A", verdict="near_ready", evidence_links=["score.json"]),
                CriticVerdict(critic_id="B", verdict="not_ready", evidence_links=["score.json"]),
            ]
        )
        self.assertEqual(consensus.status, "needs_adjudication")
        self.assertEqual(consensus.next_action.action_type, "run_third_critic_adjudication")

    def test_consensus_public_export_omits_private_rationale(self) -> None:
        consensus = ConsensusPolicy().evaluate(
            [
                CriticVerdict(
                    critic_id="A",
                    verdict="near_ready",
                    evidence_links=["score.json"],
                    private_rationale="PRIVATE_RATIONALE_SHOULD_NOT_LEAK",
                ),
                CriticVerdict(critic_id="B", verdict="near_ready", evidence_links=["score.json"]),
            ]
        )
        rendered = json.dumps(consensus.to_public_dict(), ensure_ascii=False)
        self.assertNotIn("PRIVATE_RATIONALE_SHOULD_NOT_LEAK", rendered)
