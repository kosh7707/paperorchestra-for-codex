from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.models import InputBundle
from paperorchestra.orchestra_consensus import ConsensusPolicy, CriticVerdict
from paperorchestra.orchestra_scoring import SCORE_DIMENSIONS, ScholarlyScore, ScoreDimensionAssessment, ScoringBundleBuilder
from paperorchestra.orchestra_state import HardGateStatus, OrchestraFacets, ScoreSummary
from paperorchestra.orchestrator import OrchestraOrchestrator, inspect_state
from paperorchestra.orchestra_state import NextAction, OrchestraState
from paperorchestra.session import artifact_path, create_session, save_session


def _complete_score(overall: float = 90.0, readiness_band: str = "near_ready") -> ScholarlyScore:
    return ScholarlyScore(
        overall=overall,
        readiness_band=readiness_band,
        evidence_links=["score-input.json"],
        dimensions={
            dimension: ScoreDimensionAssessment(
                score=overall,
                confidence="medium",
                rationale=f"{dimension} rationale",
                evidence_links=[f"evidence/{dimension}.json"],
            )
            for dimension in SCORE_DIMENSIONS
        },
        private_rationale="PRIVATE_SCORE_RATIONALE_SHOULD_NOT_LEAK",
    )


class OrchestratorRuntimeFacadeTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> InputBundle:
        (root / "idea.md").write_text("Synthetic idea for orchestrator runtime tests.\n", encoding="utf-8")
        (root / "experimental_log.md").write_text("Synthetic experiment log.\n", encoding="utf-8")
        (root / "template.tex").write_text("\\documentclass{article}\\begin{document}\\end{document}\n", encoding="utf-8")
        (root / "guidelines.md").write_text("Synthetic venue guidelines.\n", encoding="utf-8")
        figures = root / "figures"
        figures.mkdir()
        return InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            figures_dir=str(figures),
        )

    def _draft_session(self, root: Path, *, compiled: bool = False) -> None:
        state = create_session(root, self._write_inputs(root), allow_outside_workspace=True)
        paper = artifact_path(root, "paper.full.tex", state.session_id)
        paper.write_text("Synthetic manuscript body. PRIVATE_RAW_MANUSCRIPT_SHOULD_NOT_LEAK\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.active_artifact = "paper.full.tex"
        state.current_phase = "draft_complete"
        if compiled:
            pdf = paper.parent.parent / "build" / "compiled" / "paper.full.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"%PDF-1.5 synthetic\n")
            state.artifacts.compiled_pdf = str(pdf)
            state.active_artifact = "paper.full.pdf"
            state.current_phase = "complete"
        save_session(root, state)

    def _complete_bundle(self) -> object:
        return ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "artifacts/paper.full.tex", "score": "score-input.json"},
            compressed_evidence={"summary": "public synthetic summary"},
            private_raw_text="PRIVATE_SCORING_BUNDLE_RAW_TEXT_SHOULD_NOT_LEAK",
        )

    def test_facade_inspect_state_matches_module_function_public_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("synthetic idea\n", encoding="utf-8")
            facade_payload = OrchestraOrchestrator(root).inspect_state(material_path=material).to_public_dict()
            module_payload = inspect_state(root, material_path=material).to_public_dict()

        self.assertEqual(facade_payload, module_payload)

    def test_run_until_blocked_returns_bounded_public_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = OrchestraOrchestrator(tmp).run_until_blocked()
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["action_taken"], "none")
        self.assertTrue(payload["private_safe"])
        self.assertEqual(payload["state"]["schema_version"], "orchestra-state/1")
        self.assertIn("scorecard_summary", payload["state"])
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_result_public_dict_omits_private_notes_and_author_override_text(self) -> None:
        private = "PRIVATE_AUTHOR_OVERRIDE_SHOULD_NOT_LEAK"
        state = OrchestraState.new(
            cwd="/tmp/example",
            private_notes=["PRIVATE_NOTE_SHOULD_NOT_LEAK"],
            author_override=private,
            next_actions=[NextAction("block", "synthetic")],
        )
        result = OrchestraOrchestrator("/tmp/example")._result_from_state(state)
        rendered = json.dumps(result.to_public_dict(), ensure_ascii=False)

        self.assertNotIn("PRIVATE_NOTE_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn(private, rendered)
        self.assertIn('"author_override": "redacted"', rendered)

    def test_step_with_insufficient_material_plans_provide_material_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("synthetic idea\n", encoding="utf-8")
            result = OrchestraOrchestrator(root).step(material_path=material)
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["action_taken"], "none")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")
        self.assertNotIn("paper_full_tex", json.dumps(payload))

    def test_plan_full_loop_on_draft_session_routes_to_scoring_bundle_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._draft_session(root)
            result = OrchestraOrchestrator(root).plan_full_loop()
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_full_loop_plan")
        self.assertEqual(payload["action_taken"], "none")
        self.assertNotIn("execution_record", payload)
        self.assertEqual(payload["next_actions"][0]["action_type"], "build_scoring_bundle")
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("PRIVATE_RAW_MANUSCRIPT_SHOULD_NOT_LEAK", rendered)

    def test_plan_full_loop_hard_gate_failure_overrides_high_score(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="fail", failures=["unsupported_critical_claim"]),
            scores=ScoreSummary(overall=99.0, readiness_band="near_ready"),
        )
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=state,
            scoring_bundle=self._complete_bundle(),
            score=_complete_score(99.0),
            consensus=ConsensusPolicy().evaluate(
                [
                    CriticVerdict("A", "near_ready", ["score.json"], private_rationale="PRIVATE_CRITIC_A"),
                    CriticVerdict("B", "near_ready", ["score.json"], private_rationale="PRIVATE_CRITIC_B"),
                ]
            ),
        )
        payload = result.to_public_dict()
        actions = [action["action_type"] for action in payload["next_actions"]]

        self.assertIn(actions[0], {"start_ralph", "block"})
        self.assertNotIn("compile_current", actions)
        self.assertNotIn("export_results", actions)
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("PRIVATE_CRITIC_A", rendered)
        self.assertNotIn("PRIVATE_SCORE_RATIONALE_SHOULD_NOT_LEAK", rendered)

    def test_plan_full_loop_high_risk_without_consensus_routes_to_consensus(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(quality="near_ready"))
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=state,
            scoring_bundle=self._complete_bundle(),
            score=_complete_score(90.0),
            high_risk_readiness=True,
        )

        self.assertEqual(result.to_public_dict()["next_actions"][0]["action_type"], "run_critic_consensus")

    def test_plan_full_loop_consensus_disagreement_routes_to_third_adjudication(self) -> None:
        consensus = ConsensusPolicy().evaluate(
            [
                CriticVerdict("A", "near_ready", ["score.json"]),
                CriticVerdict("B", "not_ready", ["score.json"]),
            ]
        )
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=OrchestraState.new(cwd="/tmp/example"),
            consensus=consensus,
        )

        self.assertEqual(result.to_public_dict()["next_actions"][0]["action_type"], "run_third_critic_adjudication")

    def test_plan_full_loop_consensus_pass_on_draft_plans_compile_only(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="pass"),
        )
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "near_ready", ["score.json"]), CriticVerdict("B", "near_ready", ["score.json"])]
        )
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=state,
            scoring_bundle=self._complete_bundle(),
            score=_complete_score(90.0, "human_finalization_candidate"),
            consensus=consensus,
        )
        payload = result.to_public_dict()

        self.assertEqual(payload["next_actions"][0]["action_type"], "compile_current")
        self.assertEqual(payload["execution"], "bounded_full_loop_plan")
        self.assertNotIn("execution_record", payload)

    def test_plan_full_loop_consensus_pass_on_compiled_session_plans_export_only(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="compiled", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="pass"),
        )
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "near_ready", ["score.json"]), CriticVerdict("B", "near_ready", ["score.json"])]
        )
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=state,
            scoring_bundle=self._complete_bundle(),
            score=_complete_score(90.0, "human_finalization_candidate"),
            consensus=consensus,
        )

        self.assertEqual(result.to_public_dict()["next_actions"][0]["action_type"], "export_results")

    def test_plan_full_loop_public_payload_has_no_command_like_omx_surface(self) -> None:
        result = OrchestraOrchestrator("/tmp/example").plan_full_loop(
            state=OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(quality="near_ready")),
            scoring_bundle=self._complete_bundle(),
            score=_complete_score(90.0),
            high_risk_readiness=True,
        )
        rendered = json.dumps(result.to_public_dict(), ensure_ascii=False)

        self.assertNotIn("omx exec", rendered)
        self.assertNotIn('"omx ', rendered)


if __name__ == "__main__":
    unittest.main()
