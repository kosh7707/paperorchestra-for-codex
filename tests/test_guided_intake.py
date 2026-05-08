from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main as cli_main
from paperorchestra.intake import (
    answer_intake_question,
    approve_intake_direction,
    finalize_intake,
    get_intake_review,
    get_intake_status,
    research_prior_work,
    start_intake,
)
from paperorchestra.mcp_server import (
    tool_answer_intake_question,
    tool_approve_intake_direction,
    tool_finalize_intake,
    tool_get_intake_review,
    tool_research_prior_work,
    tool_start_intake,
)
from paperorchestra.session import load_session
class GuidedIntakeTests(unittest.TestCase):
    def _seed_minimal_review_intake(self, root: Path, **extra_answers):
        answers = {
            "method_summary": "A retrieval-augmented training method.",
            "key_results": ["Accuracy improved to 81.2% on DemoSet."],
            **extra_answers,
        }
        return start_intake(root, seed_answers=answers)

    def test_guided_intake_tracks_missing_required_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = start_intake(root)
            self.assertEqual(payload["status"], "collecting")
            self.assertIn("method_summary", payload["missing_required_keys"])
            self.assertIn("key_results", payload["missing_required_keys"])
            self.assertEqual(payload["next_question"]["key"], "method_summary")

    def test_finalize_intake_generates_inputs_and_initializes_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = start_intake(
                root,
                seed_answers={
                    "problem_statement": "We improve orchestration reliability for research-paper drafting.",
                    "method_summary": "A structured multi-agent workflow with artifact grounding and compile checks.",
                    "core_contributions": ["Guided intake", "Artifact-first pipeline"],
                    "experiments_ran": ["End-to-end mock reconstruction run", "Compile environment validation"],
                    "key_results": ["Improved onboarding clarity", "Generated submission-ready artifacts in mock mode"],
                    "baselines": ["Manual authoring workflow", "Earlier file-first PaperOrchestra flow"],
                    "figure_story": "A figure showing intake -> pipeline -> review/refine transitions.",
                    "venue": "ICLR",
                    "page_limit": 8,
                    "cutoff_date": "2024-11-01",
                },
            )
            self.assertEqual(intake["status"], "ready")
            finalized = finalize_intake(root)
            self.assertEqual(finalized["status"], "finalized")
            self.assertIn("session_id", finalized["generated_paths"])
            generated = finalized["generated_paths"]
            self.assertTrue(Path(generated["idea_path"]).exists())
            self.assertTrue(Path(generated["experimental_log_path"]).exists())
            self.assertTrue(Path(generated["guidelines_path"]).exists())
            self.assertTrue(Path(generated["template_path"]).exists())
            self.assertTrue(finalized["aggregation_paths"])
            self.assertTrue(finalized["story_candidates"])
            state = load_session(root, finalized["generated_paths"]["session_id"])
            self.assertEqual(state.inputs.cutoff_date, "2024-11-01")

    def test_finalize_intake_allows_workspace_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "template.tex").write_text("\\documentclass{article}\n\\begin{document}\\end{document}\n", encoding="utf-8")
            (root / "figs").mkdir()
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A retrieval-augmented training method.",
                    "key_results": ["Accuracy improved to 81.2% on DemoSet."],
                },
            )
            review = finalize_intake(root)
            story_id = review["story_candidates"][0]["candidate_id"]
            claim_ids = [item["candidate_id"] for item in review["claim_candidates"][:2]]
            finalized = approve_intake_direction(
                root,
                story_candidate_id=story_id,
                claim_candidate_ids=claim_ids,
                template_path="template.tex",
                figures_dir="figs",
                output_dir="outdir",
            )
            self.assertEqual(finalized["status"], "finalized")
            self.assertTrue((root / "outdir" / "template.tex").exists())

    def test_finalize_intake_requests_review_when_story_direction_is_not_user_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A new retrieval-augmented training pipeline.",
                    "key_results": ["Accuracy improved to 81.2% on the held-out benchmark."],
                },
            )
            finalized = finalize_intake(root)
            self.assertEqual(finalized["status"], "review_required")
            self.assertTrue(finalized["review_required"])
            self.assertTrue(finalized["story_candidates"])
            self.assertFalse(finalized["generated_paths"])

    def test_finalize_intake_discovers_internal_evidence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "notes.md"
            note.write_text("Ran experiment on DemoSet with a retrieval-augmented policy and saw accuracy 81.2%.", encoding="utf-8")
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A retrieval-augmented policy.",
                    "key_results": ["Accuracy improved to 81.2%."],
                    "evidence_paths": [str(note)],
                },
            )
            review_required = finalize_intake(root)
            self.assertEqual(review_required["status"], "review_required")
            evidence_registry = json.loads(Path(review_required["aggregation_paths"]["evidence_registry_path"]).read_text(encoding="utf-8"))
            self.assertTrue(evidence_registry["discovered_sources"])


    def test_finalize_intake_reports_missing_evidence_paths_as_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A retrieval-augmented policy.",
                    "key_results": ["Accuracy improved to 81.2%."],
                    "evidence_paths": ["missing-notes.md"],
                },
            )
            review_required = finalize_intake(root)
            self.assertEqual(review_required["status"], "review_required")
            self.assertTrue(review_required["warnings"])
            self.assertTrue(any("missing-notes.md" in warning for warning in review_required["warnings"]))
            status = get_intake_status(root)
            self.assertTrue(any("missing-notes.md" in warning for warning in status["warnings"]))

    def test_finalize_intake_requires_explicit_claim_approval_after_story_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A new retrieval-augmented training pipeline.",
                    "key_results": ["Accuracy improved to 81.2% on the held-out benchmark."],
                },
            )
            review_required = finalize_intake(root)
            story_id = review_required["story_candidates"][0]["candidate_id"]
            still_review_required = finalize_intake(root, selected_story_candidate_id=story_id)
            self.assertEqual(still_review_required["status"], "review_required")
            self.assertTrue(still_review_required["review_required"])
            self.assertEqual(still_review_required["selected_story_candidate_id"], story_id)
            self.assertFalse(still_review_required["selected_claim_candidate_ids"])

    def test_finalize_intake_can_finalize_after_story_and_claim_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(
                root,
                seed_answers={
                    "method_summary": "A new retrieval-augmented training pipeline.",
                    "key_results": ["Accuracy improved to 81.2% on the held-out benchmark."],
                },
            )
            review_required = finalize_intake(root)
            story_id = review_required["story_candidates"][0]["candidate_id"]
            claim_ids = [item["candidate_id"] for item in review_required["claim_candidates"][:2]]
            finalized = finalize_intake(root, selected_story_candidate_id=story_id, selected_claim_candidate_ids=claim_ids)
            self.assertEqual(finalized["status"], "finalized")
            self.assertEqual(finalized["selected_story_candidate_id"], story_id)
            self.assertEqual(finalized["selected_claim_candidate_ids"], claim_ids)
            self.assertIn("session_id", finalized["generated_paths"])

    def test_guided_intake_adds_adaptive_follow_up_for_missing_dataset_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = start_intake(
                root,
                seed_answers={
                    "method_summary": "Method",
                    "experiments_ran": ["Experiment A on benchmark X"],
                    "key_results": ["Accuracy improved"],
                },
            )
            self.assertEqual(payload["status"], "ready")
            self.assertTrue(any(item["code"] == "datasets-needed" for item in payload["adaptive_followups"]))
            self.assertEqual(payload["next_question"]["source"], "adaptive")

    def test_guided_intake_tracks_ambiguity_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collecting = start_intake(root)
            ready = answer_intake_question(
                root,
                answers={
                    "problem_statement": "Problem",
                    "method_summary": "Method",
                    "core_contributions": ["Contribution A"],
                    "experiments_ran": ["Experiment A"],
                    "key_results": ["Result A"],
                    "baselines": ["Baseline A"],
                    "figure_story": "Figure story",
                },
            )
            self.assertGreater(collecting["completion"]["ambiguity_score"], ready["completion"]["ambiguity_score"])

    def test_finalize_intake_rejects_missing_required_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(root, seed_answers={"problem_statement": "Only one answer"})
            with self.assertRaises(ValueError):
                finalize_intake(root)

    def test_finalize_intake_rejects_missing_template_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(
                root,
                seed_answers={
                    "problem_statement": "Problem",
                    "method_summary": "Method",
                    "core_contributions": ["Contribution A"],
                    "experiments_ran": ["Experiment A"],
                    "key_results": ["Result A"],
                    "baselines": ["Baseline A"],
                    "figure_story": "Figure story",
                    "template_path": str(root / "missing-template.tex"),
                },
            )
            with self.assertRaises(FileNotFoundError):
                finalize_intake(root)

    def test_intake_id_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_intake(root)
            with self.assertRaises(ValueError):
                get_intake_status(root, intake_id="../../escape-test")

    def test_finalize_intake_rejects_external_output_dir_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                start_intake(
                    root,
                    seed_answers={
                        "problem_statement": "Problem",
                        "method_summary": "Method",
                        "core_contributions": ["Contribution A"],
                        "experiments_ran": ["Experiment A"],
                        "key_results": ["Result A"],
                        "baselines": ["Baseline A"],
                        "figure_story": "Figure story",
                    },
                )
                with self.assertRaises(ValueError):
                    finalize_intake(root, output_dir=outside)
            finally:
                outside.rmdir()

    def test_finalize_intake_rejects_external_template_path_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                template = outside / "template.tex"
                template.write_text("secret\n", encoding="utf-8")
                start_intake(
                    root,
                    seed_answers={
                        "problem_statement": "Problem",
                        "method_summary": "Method",
                        "core_contributions": ["Contribution A"],
                        "experiments_ran": ["Experiment A"],
                        "key_results": ["Result A"],
                        "baselines": ["Baseline A"],
                        "figure_story": "Figure story",
                        "template_path": str(template),
                    },
                )
                with self.assertRaises(ValueError):
                    finalize_intake(root)
            finally:
                template.unlink()
                outside.rmdir()

    def test_finalize_intake_rejects_external_figures_dir_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                (outside / "figure.png").write_text("fake\n", encoding="utf-8")
                start_intake(
                    root,
                    seed_answers={
                        "problem_statement": "Problem",
                        "method_summary": "Method",
                        "core_contributions": ["Contribution A"],
                        "experiments_ran": ["Experiment A"],
                        "key_results": ["Result A"],
                        "baselines": ["Baseline A"],
                        "figure_story": "Figure story",
                        "figures_dir": str(outside),
                    },
                )
                with self.assertRaises(ValueError):
                    finalize_intake(root)
            finally:
                (outside / "figure.png").unlink()
                outside.rmdir()

    def test_finalize_intake_rejects_external_evidence_paths_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                note = outside / "note.md"
                note.write_text("external evidence\n", encoding="utf-8")
                start_intake(
                    root,
                    seed_answers={
                        "method_summary": "Method",
                        "key_results": ["Result A"],
                        "evidence_paths": [str(note)],
                    },
                )
                with self.assertRaises(ValueError):
                    finalize_intake(root)
            finally:
                note.unlink()
                outside.rmdir()

    def test_cli_intake_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli_main(["intake-start"]), 0)
                    self.assertEqual(
                        cli_main(
                            [
                                "intake-answer",
                                "--answers-json",
                                json.dumps(
                                    {
                                        "problem_statement": "Problem",
                                        "method_summary": "Method",
                                        "core_contributions": ["Contribution A", "Contribution B"],
                                        "experiments_ran": ["Experiment A"],
                                        "key_results": ["Result A"],
                                        "baselines": ["Baseline A"],
                                        "figure_story": "Figure story",
                                    }
                                ),
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(cli_main(["intake-finalize", "--allow-overwrite"]), 0)
                intake_status = get_intake_status(root)
                self.assertEqual(intake_status["status"], "finalized")
            finally:
                os.chdir(old_cwd)

    def test_mcp_intake_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            start_result = json.loads(tool_start_intake({"cwd": tmp})["content"][0]["text"])
            intake_id = start_result["intake_id"]
            answered = json.loads(
                tool_answer_intake_question(
                    {
                        "cwd": tmp,
                        "intake_id": intake_id,
                        "answers": {
                            "problem_statement": "Problem",
                            "method_summary": "Method",
                            "core_contributions": ["Contribution A"],
                            "experiments_ran": ["Experiment A"],
                            "key_results": ["Result A"],
                            "baselines": ["Baseline A"],
                            "figure_story": "Figure story",
                        },
                    }
                )["content"][0]["text"]
            )
            self.assertEqual(answered["status"], "ready")
            finalized = json.loads(tool_finalize_intake({"cwd": tmp, "intake_id": intake_id})["content"][0]["text"])
            self.assertEqual(finalized["status"], "finalized")
            self.assertIn("session_id", finalized["generated_paths"])

    def test_research_prior_work_enriches_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.md").write_text("We evaluated a retrieval model and saw 81.2% accuracy on DemoSet.", encoding="utf-8")
            self._seed_minimal_review_intake(root, evidence_paths=[str(root / "notes.md")])
            finalize_intake(root)
            enriched = research_prior_work(root, mode="mock")
            self.assertEqual(enriched["status"], "review_required")
            self.assertTrue(enriched["prior_work_candidates"])
            self.assertTrue(any(item["grounding_titles"] for item in enriched["missing_evidence_suggestions"]))

    def test_approve_preserves_prior_work_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_review_intake(root)
            finalize_intake(root)
            enriched = research_prior_work(root, mode="mock")
            story_id = enriched["story_candidates"][0]["candidate_id"]
            claim_ids = [item["candidate_id"] for item in enriched["claim_candidates"][:2]]
            approve_intake_direction(root, story_candidate_id=story_id, claim_candidate_ids=claim_ids)
            payload = get_intake_status(root)
            self.assertTrue(payload["prior_work_candidates"])
            self.assertTrue(payload["missing_evidence_suggestions"])
            self.assertTrue(any(item["grounding_titles"] for item in payload["missing_evidence_suggestions"]))

    def test_finalize_intake_auto_discovers_only_workspace_level_omx_artifacts_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".omx" / "plans").mkdir(parents=True)
            (root / ".omx" / "context").mkdir(parents=True)
            (root / ".omx" / "notepad.md").write_text("OMX note: retrieval run hit 81.2% on DemoSet.\n", encoding="utf-8")
            (root / ".omx" / "plans" / "candidate-story.md").write_text("Potential story: method-centric framing.\n", encoding="utf-8")
            (root / ".omx" / "context" / "unrelated-task.md").write_text("Old unrelated context.\n", encoding="utf-8")
            self._seed_minimal_review_intake(root)
            review_required = finalize_intake(root)
            self.assertEqual(review_required["status"], "review_required")
            evidence_registry = json.loads(Path(review_required["aggregation_paths"]["evidence_registry_path"]).read_text(encoding="utf-8"))
            discovered_sources = evidence_registry["discovered_sources"]
            self.assertTrue(any(item["relative_path"] == ".omx/notepad.md" for item in discovered_sources))
            self.assertFalse(any(item["relative_path"].startswith(".omx/plans/") for item in discovered_sources))
            self.assertFalse(any(item["relative_path"].startswith(".omx/context/") for item in discovered_sources))
            self.assertTrue(all(item["source_type"] == "omx-artifact" for item in discovered_sources))

    def test_finalize_intake_ignores_outside_workspace_symlinked_omx_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external = Path(outside) / "secret.md"
            external.write_text("external secret evidence\n", encoding="utf-8")
            (root / ".omx").mkdir()
            (root / ".omx" / "notepad.md").symlink_to(external)
            self._seed_minimal_review_intake(root)

            review_required = finalize_intake(root)

            self.assertEqual(review_required["status"], "review_required")
            evidence_registry = json.loads(Path(review_required["aggregation_paths"]["evidence_registry_path"]).read_text(encoding="utf-8"))
            discovered_sources = evidence_registry["discovered_sources"]
            self.assertFalse(any(item["path"] == str(external.resolve()) for item in discovered_sources))
            self.assertFalse(any(item["preview"] == "external secret evidence" for item in discovered_sources))

    def test_finalize_intake_ignores_outside_workspace_symlinked_omx_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external = Path(outside) / "session.json"
            external.write_text("{\"token\": \"secret\"}\n", encoding="utf-8")
            (root / ".omx" / "state").mkdir(parents=True)
            (root / ".omx" / "state" / "session.json").symlink_to(external)
            self._seed_minimal_review_intake(root)

            review_required = finalize_intake(root)

            self.assertEqual(review_required["status"], "review_required")
            evidence_registry = json.loads(Path(review_required["aggregation_paths"]["evidence_registry_path"]).read_text(encoding="utf-8"))
            discovered_sources = evidence_registry["discovered_sources"]
            self.assertFalse(any(item["path"] == str(external.resolve()) for item in discovered_sources))
            self.assertFalse(any(item["preview"] == '{\"token\": \"secret\"}' for item in discovered_sources))

    def test_research_prior_work_enforces_grounding_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_review_intake(root, baselines=["Baseline A"])
            finalize_intake(root)
            enriched = research_prior_work(root, mode="mock")
            prior_titles = {item["title"] for item in enriched["prior_work_candidates"]}
            claim_ids = {item["candidate_id"] for item in enriched["claim_candidates"]}

            self.assertTrue(prior_titles)
            self.assertTrue(claim_ids)
            for candidate in enriched["claim_candidates"]:
                self.assertTrue(candidate["basis"])
                self.assertTrue(candidate["grounding_titles"])
                self.assertTrue(set(candidate["grounding_titles"]).issubset(prior_titles))
            for candidate in enriched["story_candidates"]:
                self.assertTrue(candidate["linked_claim_ids"])
                self.assertTrue(set(candidate["linked_claim_ids"]).issubset(claim_ids))
                self.assertTrue(candidate["grounding_titles"])
                self.assertTrue(set(candidate["grounding_titles"]).issubset(prior_titles))
            for suggestion in enriched["missing_evidence_suggestions"]:
                self.assertTrue(set(suggestion["grounding_titles"]).issubset(prior_titles))

    def test_get_intake_review_matches_review_summary_artifact_after_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_review_intake(root, baselines=["Baseline A"])
            finalize_intake(root)
            research_prior_work(root, mode="mock")
            review_packet = get_intake_review(root)
            review_summary = json.loads(Path(review_packet["aggregation_paths"]["review_summary_path"]).read_text(encoding="utf-8"))

            self.assertEqual(
                [item["candidate_id"] for item in review_packet["story_candidates"]],
                [item["candidate_id"] for item in review_summary["story_candidates"]],
            )
            self.assertEqual(
                [item["candidate_id"] for item in review_packet["claim_candidates"]],
                [item["candidate_id"] for item in review_summary["claim_candidates"]],
            )
            self.assertEqual(
                [item["title"] for item in review_packet["prior_work_candidates"]],
                [item["title"] for item in review_summary["prior_work_candidates"]],
            )
            self.assertEqual(
                [item["code"] for item in review_packet["missing_evidence_suggestions"]],
                [item["code"] for item in review_summary["missing_evidence_suggestions"]],
            )

    def test_mcp_finalize_ignores_outside_workspace_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                note = outside / "secret.md"
                note.write_text("external evidence\n", encoding="utf-8")
                start_result = json.loads(tool_start_intake({"cwd": str(root)})["content"][0]["text"])
                intake_id = start_result["intake_id"]
                json.loads(
                    tool_answer_intake_question(
                        {
                            "cwd": str(root),
                            "intake_id": intake_id,
                            "answers": {
                                "method_summary": "Method",
                                "key_results": ["Result A"],
                                "evidence_paths": [str(note)],
                            },
                        }
                    )["content"][0]["text"]
                )
                with self.assertRaises(ValueError):
                    json.loads(
                        tool_finalize_intake(
                            {
                                "cwd": str(root),
                                "intake_id": intake_id,
                                "allow_outside_workspace": True,
                            }
                        )["content"][0]["text"]
                    )
            finally:
                note.unlink()
                outside.rmdir()

    def test_approve_intake_direction_finalizes_from_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_minimal_review_intake(root)
            review = finalize_intake(root)
            story_id = review["story_candidates"][0]["candidate_id"]
            claim_ids = [item["candidate_id"] for item in review["claim_candidates"][:2]]
            finalized = approve_intake_direction(root, story_candidate_id=story_id, claim_candidate_ids=claim_ids)
            self.assertEqual(finalized["status"], "finalized")
            self.assertEqual(finalized["selected_story_candidate_id"], story_id)

    def test_mcp_review_and_approve_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            start_result = json.loads(tool_start_intake({"cwd": tmp})["content"][0]["text"])
            intake_id = start_result["intake_id"]
            json.loads(
                tool_answer_intake_question(
                    {
                        "cwd": tmp,
                        "intake_id": intake_id,
                        "answers": {
                            "method_summary": "A retrieval-augmented training method.",
                            "key_results": ["Accuracy improved to 81.2% on DemoSet."],
                        },
                    }
                )["content"][0]["text"]
            )
            review = json.loads(tool_finalize_intake({"cwd": tmp, "intake_id": intake_id})["content"][0]["text"])
            self.assertEqual(review["status"], "review_required")
            enriched = json.loads(tool_research_prior_work({"cwd": tmp, "intake_id": intake_id, "mode": "mock"})["content"][0]["text"])
            self.assertTrue(enriched["prior_work_candidates"])
            packet = json.loads(tool_get_intake_review({"cwd": tmp, "intake_id": intake_id})["content"][0]["text"])
            story_id = packet["story_candidates"][0]["candidate_id"]
            claim_ids = [item["candidate_id"] for item in packet["claim_candidates"][:2]]
            approved = json.loads(
                tool_approve_intake_direction(
                    {
                        "cwd": tmp,
                        "intake_id": intake_id,
                        "story_candidate_id": story_id,
                        "claim_candidate_ids": claim_ids,
                    }
                )["content"][0]["text"]
            )
            self.assertEqual(approved["status"], "finalized")
            self.assertIn("session_id", approved["generated_paths"])


if __name__ == "__main__":
    unittest.main()
