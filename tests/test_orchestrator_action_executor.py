from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_executor import (
    FAKE_SUPPORTED_ACTIONS,
    LOCAL_SUPPORTED_ACTIONS,
    ActionExecutionPolicy,
    ExecutionRecord,
    FakeActionExecutor,
    LocalActionExecutor,
)
from paperorchestra.orchestra_planner import KNOWN_ACTIONS
from paperorchestra.orchestra_state import NextAction, OrchestraFacets, OrchestraState
from paperorchestra.orchestrator import OrchestraOrchestrator, _apply_local_execution_record


class OrchestratorActionExecutorTests(unittest.TestCase):
    def _write_materials(self, root: str) -> None:
        material = Path(root)
        (material / "idea.md").write_text(
            "PaperOrchestra improves manuscript safety by separating claims from evidence. "
            "The system reduces citation uncertainty compared with ad hoc drafting.",
            encoding="utf-8",
        )
        (material / "experiment_log.md").write_text(
            "Experiment results show 12 checklist violations were caught before drafting. "
            "The workflow improves reviewability by preserving artifact evidence.",
            encoding="utf-8",
        )

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

        self.assertEqual(result.execution, "bounded_fake_execution")
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

    def test_local_executor_inspect_material_returns_public_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_materials(tmp)
            record = LocalActionExecutor(material_path=tmp).execute(
                NextAction("inspect_material", "material_inventory_needed"),
                OrchestraState.new(cwd=tmp),
            )

        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)
        self.assertEqual(record.status, "executed_local")
        self.assertTrue(record.succeeded)
        self.assertIn("material_inventory", rendered)
        self.assertIn("redacted-material:", rendered)
        self.assertNotIn("idea.md", rendered)
        self.assertNotIn("PaperOrchestra improves manuscript safety", rendered)

    def test_local_executor_build_source_digest_returns_public_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_materials(tmp)
            record = LocalActionExecutor(material_path=tmp).execute(
                NextAction("build_source_digest", "source_digest_missing"),
                OrchestraState.new(cwd=tmp),
            )

        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)
        self.assertEqual(record.status, "executed_local")
        self.assertIn("source_digest", rendered)
        self.assertNotIn(tmp, rendered)
        self.assertNotIn("experiment_log.md", rendered)

    def test_local_executor_build_claim_graph_omits_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_materials(tmp)
            record = LocalActionExecutor(material_path=tmp).execute(
                NextAction("build_claim_graph", "claim_graph_missing"),
                OrchestraState.new(cwd=tmp),
            )

        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)
        self.assertEqual(record.status, "executed_local")
        self.assertIn("claim_graph", rendered)
        self.assertIn("redacted-claim:", rendered)
        self.assertNotIn("raw_text", rendered)
        self.assertNotIn("reduces citation uncertainty", rendered)

    def test_local_executor_build_claim_graph_blocks_on_insufficient_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "notes.md").write_text("too short", encoding="utf-8")
            record = LocalActionExecutor(material_path=tmp).execute(
                NextAction("build_claim_graph", "claim_graph_missing"),
                OrchestraState.new(cwd=tmp),
            )

        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)
        self.assertEqual(record.status, "blocked")
        self.assertFalse(record.succeeded)
        self.assertIn("source_digest", rendered)
        self.assertIn("insufficient_material", rendered)

    def test_local_executor_blocks_when_material_path_is_missing(self) -> None:
        record = LocalActionExecutor().execute(
            NextAction("inspect_material", "material_inventory_needed"),
            OrchestraState.new(cwd="/tmp/example"),
        )

        self.assertEqual(record.status, "blocked")
        self.assertFalse(record.succeeded)

    def test_local_executor_omx_action_is_unsupported(self) -> None:
        record = LocalActionExecutor(material_path="/tmp/example").execute(
            NextAction("start_autoresearch", "research_needed", requires_omx=True),
            OrchestraState.new(cwd="/tmp/example"),
        )

        self.assertEqual(record.status, "unsupported")
        self.assertFalse(record.succeeded)

    def test_local_executor_build_scoring_bundle_uses_current_state_summary(self) -> None:
        record = LocalActionExecutor().execute(
            NextAction("build_scoring_bundle", "scorecard_needed"),
            OrchestraState.new(cwd="/tmp/example"),
        )
        rendered = json.dumps(record.to_public_dict(), ensure_ascii=False)

        self.assertEqual(record.status, "executed_local")
        self.assertIn("scorecard_summary", rendered)
        self.assertIn("orchestra-scorecard-summary/1", rendered)

    def test_policy_classifies_every_known_action(self) -> None:
        policy = ActionExecutionPolicy()
        classifications = {name: policy.classify(NextAction(name, "contract_test")).execution_kind for name in KNOWN_ACTIONS}

        self.assertNotIn("unsupported", classifications.values())

    def test_policy_local_supported_and_fake_executor_sets_are_explicit(self) -> None:
        policy = ActionExecutionPolicy()
        policy_local_supported = {
            name
            for name in KNOWN_ACTIONS
            if policy.classify(NextAction(name, "contract_test")).execution_kind == "local_supported"
        }

        self.assertEqual(policy_local_supported, LOCAL_SUPPORTED_ACTIONS)
        self.assertEqual(
            FAKE_SUPPORTED_ACTIONS,
            {"provide_material", "inspect_material", "build_source_digest", "build_claim_graph", "build_scoring_bundle", "block"},
        )
        self.assertEqual(policy.classify(NextAction("provide_material", "user_input_needed")).execution_kind, "adapter_required")
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
            "run_critic_consensus": "$critic-consensus",
            "run_third_critic_adjudication": "$critic-adjudication",
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
            "provide_material",
            "compile_current",
            "export_results",
            "match_supplied_figures",
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
        self.assertNotIn("omx exec", rendered)

    def test_policy_classifies_full_loop_actions_public_safely(self) -> None:
        policy = ActionExecutionPolicy()
        consensus = policy.classify(NextAction("run_critic_consensus", "contract_test"))
        adjudication = policy.classify(NextAction("run_third_critic_adjudication", "contract_test"))
        figure_match = policy.classify(NextAction("match_supplied_figures", "contract_test"))

        self.assertEqual(consensus.execution_kind, "omx_required")
        self.assertEqual(consensus.omx_surface, "$critic-consensus")
        self.assertEqual(adjudication.execution_kind, "omx_required")
        self.assertEqual(adjudication.omx_surface, "$critic-adjudication")
        self.assertEqual(figure_match.execution_kind, "adapter_required")
        rendered = json.dumps(
            [consensus.to_public_dict(), adjudication.to_public_dict(), figure_match.to_public_dict()],
            ensure_ascii=False,
        )
        self.assertNotIn("omx exec", rendered)
        self.assertNotIn('"omx ', rendered)

    def test_policy_redacts_deprecated_command_like_unknown_action(self) -> None:
        capability = ActionExecutionPolicy().classify(NextAction("omx autoresearch", "deprecated"))
        rendered = json.dumps(capability.to_public_dict(), ensure_ascii=False)

        self.assertEqual(capability.execution_kind, "unsupported")
        self.assertNotIn("omx autoresearch", rendered)
        self.assertIn("<unsupported-action>", rendered)

    def test_step_with_local_executor_advances_claim_graph_state_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_materials(tmp)
            orchestrator = OrchestraOrchestrator(tmp)
            result = orchestrator.step(material_path=tmp, execute=True, executor=LocalActionExecutor(material_path=tmp))
            payload = result.to_public_dict()

        self.assertEqual(payload["action_taken"], "build_claim_graph")
        self.assertEqual(payload["execution"], "bounded_local_execution")
        self.assertEqual(payload["execution_record"]["status"], "executed_local")
        self.assertEqual(result.state.facets.claims, "candidate")
        self.assertEqual(result.state.facets.evidence, "research_needed")
        self.assertEqual(result.state.facets.citations, "unknown_refs")
        self.assertEqual(result.state.readiness.label, "research_needed")
        self.assertNotEqual(result.state.facets.writing, "drafting_allowed")
        self.assertEqual(result.state.next_actions[0].action_type, "start_autoresearch")
        self.assertEqual(result.state.next_actions[0].omx_surface, "$autoresearch")
        self.assertTrue(any(ref.get("kind") == "orchestrator_execution_record" for ref in result.state.evidence_refs))
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("paper_full_tex", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn("codex ", rendered)

    def test_fake_executor_does_not_advance_state_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = OrchestraOrchestrator(tmp).step(execute=True, executor=FakeActionExecutor())

        self.assertEqual(result.execution, "bounded_fake_execution")
        self.assertEqual(result.state.facets.claims, "missing")
        self.assertEqual(result.state.readiness.label, "needs_material")

    def test_apply_local_source_digest_record_advances_to_claim_graph_action(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(material="inventory_needed", source_digest="missing"),
        )
        state.next_actions = [NextAction("inspect_material", "material_inventory_needed")]
        _apply_local_execution_record(
            state,
            {
                "action_type": "build_source_digest",
                "status": "executed_local",
                "adapter": "local",
                "evidence_refs": [
                    {
                        "kind": "source_digest",
                        "payload": {
                            "schema_version": "source-digest/1",
                            "sufficient": True,
                            "private_safe_summary": True,
                        },
                    }
                ],
            },
        )

        self.assertEqual(state.facets.material, "inventoried_sufficient")
        self.assertEqual(state.facets.source_digest, "ready")
        self.assertEqual(state.facets.artifacts, "fresh")
        self.assertEqual(state.next_actions[0].action_type, "build_claim_graph")

    def test_apply_local_inspect_material_record_does_not_claim_digest_readiness(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(material="inventory_needed", source_digest="missing"),
        )
        state.next_actions = [NextAction("inspect_material", "material_inventory_needed")]
        _apply_local_execution_record(
            state,
            {
                "action_type": "inspect_material",
                "status": "executed_local",
                "adapter": "local",
                "evidence_refs": [
                    {
                        "kind": "material_inventory",
                        "payload": {
                            "schema_version": "material-inventory/1",
                            "file_count": 2,
                            "private_safe_summary": True,
                        },
                    }
                ],
            },
        )

        self.assertNotEqual(state.facets.source_digest, "ready")
        self.assertNotEqual(state.next_actions[0].action_type, "build_claim_graph")

    def test_apply_local_malformed_claim_graph_record_does_not_advance(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(material="inventoried_sufficient", source_digest="ready", claims="missing"),
        )
        state.next_actions = [NextAction("build_claim_graph", "claim_graph_missing")]
        _apply_local_execution_record(
            state,
            {
                "action_type": "build_claim_graph",
                "status": "executed_local",
                "adapter": "local",
                "evidence_refs": [
                    {
                        "kind": "claim_graph",
                        "payload": {
                            "schema_version": "claim-graph/1",
                            "ready": True,
                            "evidence_obligations": [],
                            "citation_obligations": [],
                        },
                    }
                ],
            },
        )

        self.assertEqual(state.facets.claims, "missing")
        self.assertEqual(state.next_actions[0].action_type, "build_claim_graph")

    def test_apply_local_malformed_source_digest_record_does_not_advance(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(material="inventory_needed", source_digest="missing", artifacts="unknown"),
        )
        state.next_actions = [NextAction("build_source_digest", "source_digest_missing")]
        _apply_local_execution_record(
            state,
            {
                "action_type": "build_source_digest",
                "status": "executed_local",
                "adapter": "local",
                "evidence_refs": [
                    {
                        "kind": "source_digest",
                        "payload": {
                            "schema_version": "source-digest/1",
                            "sufficient": True,
                        },
                    }
                ],
            },
        )

        self.assertEqual(state.facets.material, "inventory_needed")
        self.assertEqual(state.facets.source_digest, "missing")
        self.assertEqual(state.facets.artifacts, "unknown")
        self.assertEqual(state.next_actions[0].action_type, "build_source_digest")

    def test_apply_local_no_evidence_record_does_not_advance(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(material="inventoried_sufficient", source_digest="ready", claims="missing"),
        )
        state.next_actions = [NextAction("build_claim_graph", "claim_graph_missing")]
        _apply_local_execution_record(
            state,
            {
                "action_type": "build_claim_graph",
                "status": "executed_local",
                "adapter": "local",
                "evidence_refs": [],
            },
        )

        self.assertEqual(state.facets.claims, "missing")
        self.assertEqual(state.next_actions[0].action_type, "build_claim_graph")


if __name__ == "__main__":
    unittest.main()
