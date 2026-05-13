from __future__ import annotations

import json
import tempfile
import unittest

from paperorchestra.orchestra_executor import (
    FAKE_SUPPORTED_ACTIONS,
    ActionExecutionPolicy,
    ExecutionRecord,
    FakeActionExecutor,
)
from paperorchestra.orchestra_planner import KNOWN_ACTIONS
from paperorchestra.orchestra_state import NextAction, OrchestraFacets, OrchestraState
from paperorchestra.orchestrator import OrchestraOrchestrator


class OrchestratorActionExecutorTests(unittest.TestCase):
    def test_default_step_has_no_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = OrchestraOrchestrator(tmp).step().to_public_dict()

        self.assertEqual(payload["action_taken"], "none")
        self.assertNotIn("execution_record", payload)

    def test_fake_executor_provide_material_returns_public_execution_record(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example")
        action = NextAction("provide_material", "no_session_or_material")
        record = FakeActionExecutor().execute(action, state)
        payload = record.to_public_dict()

        self.assertEqual(payload["schema_version"], "orchestrator-execution-record/1")
        self.assertEqual(payload["action_type"], "provide_material")
        self.assertEqual(payload["status"], "executed_fake")
        self.assertEqual(payload["adapter"], "fake")
        self.assertTrue(payload["state_rebuild_required"])
        self.assertTrue(payload["evidence_refs"])
        self.assertTrue(payload["private_safe"])

    def test_step_execute_true_requires_explicit_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                OrchestraOrchestrator(tmp).step(execute=True)

    def test_step_with_fake_executor_appends_execution_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = OrchestraOrchestrator(tmp)
            before = orchestrator.inspect_state()
            result = orchestrator.step(execute=True, executor=FakeActionExecutor())
            payload = result.to_public_dict()

        self.assertEqual(payload["action_taken"], "provide_material")
        self.assertIn("execution_record", payload)
        self.assertEqual(payload["execution_record"]["status"], "executed_fake")
        self.assertEqual(result.state.facets.to_dict(), before.facets.to_dict())
        self.assertEqual(result.state.readiness.to_dict(), before.readiness.to_dict())
        self.assertEqual(result.state.scores.to_dict(), before.scores.to_dict())
        self.assertEqual(result.state.hard_gates.to_dict(), before.hard_gates.to_dict())
        self.assertNotIn("paper_full_tex", json.dumps(payload))
        self.assertTrue(any(ref.get("kind") == "orchestrator_execution_record" for ref in result.state.evidence_refs))

    def test_fake_execution_does_not_enable_drafting_or_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = OrchestraOrchestrator(tmp).step(execute=True, executor=FakeActionExecutor())

        self.assertNotEqual(result.state.facets.writing, "drafting_allowed")
        self.assertNotEqual(result.state.readiness.status, "ready")

    def test_step_rejects_executor_state_mutation(self) -> None:
        class MutatingExecutor:
            def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
                state.facets.writing = "drafting_allowed"
                return ExecutionRecord(
                    action_type=action.action_type,
                    reason=action.reason,
                    status="executed_fake",
                    adapter="mutating",
                )

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "must not mutate OrchestraState"):
                OrchestraOrchestrator(tmp).step(execute=True, executor=MutatingExecutor())

    def test_unsupported_action_returns_unsupported_without_success(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(evidence="research_needed"),
            next_actions=[NextAction("start_autoresearch", "research_needed", requires_omx=True)],
        )
        record = FakeActionExecutor().execute(state.next_actions[0], state)

        self.assertEqual(record.status, "unsupported")
        self.assertFalse(record.succeeded)
        self.assertFalse(record.state_rebuild_required)

    def test_execution_record_public_dict_redacts_private_fields(self) -> None:
        record = ExecutionRecord(
            action_type="provide_material",
            reason="synthetic",
            status="executed_fake",
            adapter="fake",
            evidence_refs=[{"kind": "synthetic", "payload": {"raw_text": "PRIVATE_RAW_SHOULD_NOT_LEAK"}}],
            private_detail="PRIVATE_DETAIL_SHOULD_NOT_LEAK",
        )
        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertNotIn("PRIVATE_RAW_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("PRIVATE_DETAIL_SHOULD_NOT_LEAK", rendered)
        self.assertIn("<redacted>", rendered)

    def test_policy_classifies_every_known_action(self) -> None:
        policy = ActionExecutionPolicy()
        classifications = {name: policy.classify(NextAction(name, "contract_test")).execution_kind for name in KNOWN_ACTIONS}

        self.assertNotIn("unsupported", classifications.values())

    def test_policy_fake_supported_matches_fake_executor_except_terminal_block(self) -> None:
        policy = ActionExecutionPolicy()
        policy_fake_supported = {
            name
            for name in KNOWN_ACTIONS
            if policy.classify(NextAction(name, "contract_test")).execution_kind == "fake_supported"
        }

        self.assertEqual(policy_fake_supported, FAKE_SUPPORTED_ACTIONS - {"block"})
        self.assertEqual(policy.classify(NextAction("block", "terminal")).execution_kind, "terminal_block")

    def test_policy_omx_actions_use_canonical_surfaces(self) -> None:
        expected = {
            "start_autoresearch": "$autoresearch",
            "start_autoresearch_goal": "$autoresearch-goal",
            "start_deep_interview": "$deep-interview",
            "start_ralplan": "$ralplan",
            "start_ralph": "$ralph",
            "start_ultraqa": "$ultraqa",
            "record_trace_summary": "$trace",
        }
        policy = ActionExecutionPolicy()

        for action_type, surface in expected.items():
            with self.subTest(action_type=action_type):
                capability = policy.classify(NextAction(action_type, "contract_test", omx_surface=None))
                self.assertEqual(capability.execution_kind, "omx_required")
                self.assertTrue(capability.requires_omx)
                self.assertEqual(capability.omx_surface, surface)

    def test_policy_adapter_required_actions_are_not_fake_supported(self) -> None:
        policy = ActionExecutionPolicy()
        for action_type in {
            "build_evidence_obligations",
            "show_prewriting_notice",
            "re_adjudicate",
            "auto_weaken_or_delete_claim",
            "compile_current",
            "export_results",
        }:
            with self.subTest(action_type=action_type):
                capability = policy.classify(NextAction(action_type, "contract_test"))
                self.assertEqual(capability.execution_kind, "adapter_required")

    def test_policy_unknown_action_is_unsupported(self) -> None:
        capability = ActionExecutionPolicy().classify(NextAction("legacy_unknown", "contract_test"))

        self.assertEqual(capability.execution_kind, "unsupported")
        self.assertEqual(capability.adapter_hint, "none")

    def test_policy_normalizes_invalid_public_risk(self) -> None:
        capability = ActionExecutionPolicy().classify(NextAction("provide_material", "contract_test", risk="PRIVATE_RISK"))

        self.assertEqual(capability.risk, "unknown")

    def test_capability_public_dict_is_private_safe(self) -> None:
        capability = ActionExecutionPolicy().classify(
            NextAction(
                "provide_material",
                "PRIVATE_REASON_SHOULD_NOT_LEAK",
                risk="PRIVATE_RISK",
            )
        )
        rendered = json.dumps(capability.to_public_dict(), ensure_ascii=False)

        self.assertNotIn("PRIVATE_REASON_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("PRIVATE_RISK", rendered)
        self.assertNotIn("raw_text", rendered)
        self.assertNotIn("argv", rendered)
        self.assertIn('"private_safe": true', rendered)

    def test_policy_output_does_not_use_deprecated_omx_autoresearch_command(self) -> None:
        policy = ActionExecutionPolicy()
        rendered = json.dumps(
            [policy.classify(NextAction(name, "contract_test")).to_public_dict() for name in KNOWN_ACTIONS],
            ensure_ascii=False,
        )

        self.assertNotIn("omx autoresearch", rendered)

    def test_policy_redacts_deprecated_command_like_unknown_action(self) -> None:
        capability = ActionExecutionPolicy().classify(NextAction("omx autoresearch", "deprecated"))
        rendered = json.dumps(capability.to_public_dict(), ensure_ascii=False)

        self.assertEqual(capability.execution_kind, "unsupported")
        self.assertNotIn("omx autoresearch", rendered)
        self.assertIn("<unsupported-action>", rendered)


if __name__ == "__main__":
    unittest.main()
