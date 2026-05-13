from __future__ import annotations

import json
import tempfile
import unittest

from paperorchestra.orchestra_planner import KNOWN_ACTIONS
from paperorchestra.orchestra_policies import ReadinessPolicy, StateValidator
from paperorchestra.orchestra_state import HardGateStatus, OrchestraFacets, OrchestraState, ScoreSummary


class OrchestraStateContractTests(unittest.TestCase):
    def test_state_defaults_are_non_ready_and_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = OrchestraState.new(cwd=tmp)
            payload = state.to_dict()
            restored = OrchestraState.from_dict(json.loads(json.dumps(payload)))

        self.assertEqual(restored.schema_version, "orchestra-state/1")
        self.assertEqual(restored.facets.session, "no_session")
        self.assertEqual(restored.facets.material, "missing")
        self.assertEqual(restored.readiness.label, "needs_material")
        self.assertIn("materials", restored.five_axis_status)
        self.assertIn("readiness", restored.five_axis_status)

    def test_hard_gate_failure_overrides_high_score(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="fail", failures=["unsupported_critical_claim"]),
            scores=ScoreSummary(overall=98.0, readiness_band="human_finalization_candidate"),
        )
        updated = ReadinessPolicy().apply(state)

        self.assertEqual(updated.readiness.label, "not_ready")
        self.assertIn("unsupported_critical_claim", updated.blocking_reasons)

    def test_author_override_cannot_force_readiness(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(claims="conflict", evidence="unresolved", interaction="answered"),
            author_override="force_ready_despite_conflict",
        )
        updated = ReadinessPolicy().apply(state)
        validation = StateValidator().validate(updated)

        self.assertNotEqual(updated.readiness.label, "ready_for_human_finalization")
        self.assertIn("author_override_conflicts_with_evidence", updated.blocking_reasons)
        self.assertFalse(validation.valid)

    def test_public_safe_export_omits_private_raw_fields(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            private_notes=["PRIVATE_RAW_REFERENCE_TEXT_SHOULD_NOT_LEAK"],
        )
        public_payload = state.to_public_dict()
        rendered = json.dumps(public_payload, ensure_ascii=False)

        self.assertNotIn("PRIVATE_RAW_REFERENCE_TEXT_SHOULD_NOT_LEAK", rendered)
        self.assertTrue(public_payload["private_safe"])


    def test_five_axis_readiness_does_not_hide_hard_gate_failure(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(quality="near_ready"),
            hard_gates=HardGateStatus(status="fail", failures=["unknown_critical_reference"]),
            scores=ScoreSummary(overall=91.0, readiness_band="near_ready"),
        )
        updated = ReadinessPolicy().apply(state)

        self.assertEqual(updated.readiness.label, "not_ready")
        self.assertEqual(updated.five_axis_status["readiness"], "not_ready")

    def test_public_safe_export_redacts_author_override_text(self) -> None:
        private_override = "PRIVATE_AUTHOR_CLAIM_SHOULD_NOT_LEAK"
        state = OrchestraState.new(cwd="/tmp/example", author_override=private_override)
        public_payload = state.to_public_dict()
        rendered = json.dumps(public_payload, ensure_ascii=False)

        self.assertNotIn(private_override, rendered)
        self.assertEqual(public_payload.get("author_override"), "redacted")

    def test_deprecated_omx_autoresearch_command_is_not_a_known_action(self) -> None:
        rendered = json.dumps(KNOWN_ACTIONS, ensure_ascii=False)
        self.assertNotIn("omx autoresearch", rendered)
        self.assertIn("start_autoresearch", KNOWN_ACTIONS)
        self.assertIn("start_autoresearch_goal", KNOWN_ACTIONS)


if __name__ == "__main__":
    unittest.main()
