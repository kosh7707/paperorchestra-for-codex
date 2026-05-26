from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main
from paperorchestra.human_needed import record_human_needed_answer
from paperorchestra.io_utils import read_json
from paperorchestra.mcp_server import TOOL_HANDLERS
from paperorchestra.operator_feedback import (
    _load_imported_feedback,
    apply_operator_feedback,
    build_operator_review_packet,
    derive_operator_issue_id,
    import_operator_feedback,
)
from paperorchestra.pipeline import ContractError
from paperorchestra.providers import MockProvider
from paperorchestra.session import artifact_path, load_session, save_session

from tests.pipeline_test_support import PipelineTestCase


PRIVATE_PHRASE = "PRIVATE_AUTHOR_DECISION_DO_NOT_EXPORT"
FORBIDDEN_OPERATOR_NOTE_CASES = (
    ("answer_text", {"nested": {"answer_text": PRIVATE_PHRASE}}),
    ("private_answer_path", {"nested": {"private_answer_path": "/private/answer.json"}}),
    ("private_path", {"nested": {"private_path": "/private/location"}}),
    ("raw", {"nested": {"raw": PRIVATE_PHRASE}}),
    ("raw_answer", {"items": [{"raw_answer": PRIVATE_PHRASE}]}),
    ("answer_not_redacted", {"items": [{"nested": {"answer": PRIVATE_PHRASE}}]}),
)


class HumanNeededLoopTests(PipelineTestCase):
    def _session_with_human_plan(self, root: Path):
        state = self._init_session_with_minimal_inputs(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft claim.\n\\end{document}\n",
            encoding="utf-8",
        )
        state.artifacts.paper_full_tex = str(paper)
        save_session(root, state)
        plan_path = self._write_terminal_human_needed_plan(root)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["repair_actions"] = [
            {
                "id": "quality-eval:citation-support-manual-author",
                "code": "citation_support_manual_check_requires_author_judgment",
                "automation": "human_needed",
                "target": "claim safety",
                "reason": "Author/operator must decide whether to weaken the claim.",
            }
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return state, paper, plan_path

    def _write_ready_candidate_execution(self, root: Path, paper: Path, candidate_text: str = "Approved candidate.") -> Path:
        candidate = root / "candidate.tex"
        candidate.write_text(
            "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
            + candidate_text
            + "\n\\end{document}\n",
            encoding="utf-8",
        )
        candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-001.json"
        execution_payload = {
            "schema_version": "qa-loop-execution/1",
            "verdict": "human_needed",
            "candidate_approval": {
                "status": "human_needed_candidate_ready",
                "candidate_path": str(candidate),
                "candidate_sha256": "sha256:" + candidate_sha,
                "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "source_execution_path": str(execution_path),
                "source_execution_sha256": "pending",
                "created_at": "2026-05-20T00:00:00+00:00",
            },
            "candidate_progress": {
                "forward_progress": True,
                "before_failing_codes": ["citation_support_manual_check"],
                "after_failing_codes": [],
            },
        }
        execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
        execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
        return execution_path

    def test_answer_human_needed_records_private_raw_and_public_redacted_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, _paper, _plan = self._session_with_human_plan(root)

            result = record_human_needed_answer(
                root,
                answer=f"Please weaken the risky claim. {PRIVATE_PHRASE}",
                intent="generate_new_operator_candidate",
            )

            self.assertEqual(result["answer"], "redacted")
            self.assertEqual(result["decision_kind"], "generate_new_operator_candidate")
            self.assertEqual(result["handoff_type"], "citation_author_judgment")
            self.assertIn("answer_sha256", result)
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(result))

            public_path = Path(result["public_answer_artifact"])
            self.assertTrue(public_path.exists())
            public_payload = read_json(public_path)
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(public_payload))
            self.assertNotIn("private_answer_path", json.dumps(public_payload))
            self.assertNotIn("packet_path", public_payload)
            self.assertNotIn("feedback_path", public_payload)
            self.assertNotIn("public_answer_artifact", public_payload)
            self.assertEqual(public_payload["session_id"], state.session_id)
            self.assertEqual(public_payload["decision_kind"], "generate_new_operator_candidate")

            private_root = root / ".paper-orchestra" / "private" / "human-needed"
            private_files = list(private_root.rglob("*.json"))
            self.assertEqual(len(private_files), 1)
            self.assertIn(PRIVATE_PHRASE, private_files[0].read_text(encoding="utf-8"))

            feedback = read_json(result["feedback_path"])
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(feedback))
            self.assertEqual(feedback["human_needed_answer"]["answer_sha256"], result["answer_sha256"])

    def test_answer_human_needed_rejects_raw_output_to_trackable_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            bad_path = root / "docs" / "raw-answer.json"
            bad_path.parent.mkdir()

            with self.assertRaisesRegex(ContractError, "private answer output"):
                record_human_needed_answer(
                    root,
                    answer="private answer",
                    output_answer=bad_path,
                    intent="generate_new_operator_candidate",
                )

    def test_answer_human_needed_rejects_tampered_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            packet_path, _packet = build_operator_review_packet(root, review_scope="tex_only")
            packet_path.write_text(packet_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            with self.assertRaises(ContractError):
                record_human_needed_answer(
                    root,
                    answer="Use the weaker supported claim.",
                    packet_path=packet_path,
                    intent="generate_new_operator_candidate",
                )

    def test_answer_human_needed_rejects_stale_packet_for_current_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, paper, _plan = self._session_with_human_plan(root)
            packet_path, _packet = build_operator_review_packet(root, review_scope="tex_only")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nChanged after packet.\n\\end{document}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractError, "current session"):
                record_human_needed_answer(
                    root,
                    answer="Use the weaker supported claim.",
                    packet_path=packet_path,
                    intent="generate_new_operator_candidate",
                )

    def test_answer_human_needed_rejects_packet_when_current_plan_no_longer_operator_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, _paper, plan_path = self._session_with_human_plan(root)
            packet_path, _packet = build_operator_review_packet(root, review_scope="tex_only")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["verdict"] = "ready_for_human_finalization"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaises(ContractError):
                record_human_needed_answer(
                    root,
                    answer="Use the weaker supported claim.",
                    packet_path=packet_path,
                    intent="generate_new_operator_candidate",
                )

    def test_answer_human_needed_fails_closed_for_ambiguous_multiple_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, _paper, plan_path = self._session_with_human_plan(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["repair_actions"].append(
                {
                    "id": "quality-eval:figure-grounding:figure_caption_plot_purpose_mismatch:2",
                    "code": "figure_caption_plot_purpose_mismatch",
                    "automation": "human_needed",
                    "target": "fig:overview",
                    "reason": "Figure placement needs operator judgment.",
                }
            )
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "multiple human_needed actions"):
                record_human_needed_answer(
                    root,
                    answer="Do the safer thing.",
                    intent="generate_new_operator_candidate",
                )

    def test_answer_human_needed_can_target_active_candidate_approval_when_plan_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, paper, plan_path = self._session_with_human_plan(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["verdict"] = "continue"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            self._write_ready_candidate_execution(root, paper)

            result = record_human_needed_answer(
                root,
                answer="Approve the candidate.",
                intent="approve_existing_candidate",
                review_scope="tex_only",
            )

            feedback = read_json(result["feedback_path"])
            self.assertEqual(feedback["intent"], "approve_existing_candidate")
            self.assertEqual(feedback["issues"][0]["source_artifact_role"], "qa_loop_execution")
            self.assertIn("packet-bound candidate_approval", feedback["issues"][0]["suggested_action"])
            self.assertIn("operator-feedback hard gate", feedback["issues"][0]["suggested_action"])
            self.assertEqual(result["handoff_type"], "candidate_approval")

    def test_answer_human_needed_generic_proceed_words_do_not_approve_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, paper, plan_path = self._session_with_human_plan(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["verdict"] = "continue"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            self._write_ready_candidate_execution(root, paper)

            for answer in ["좋아, 계속 진행해.", "반영해서 진행해.", "Looks good, continue."]:
                result = record_human_needed_answer(root, answer=answer, review_scope="tex_only")
                self.assertEqual(result["decision_kind"], "generate_new_operator_candidate")

    def test_answer_human_needed_reject_phrase_wins_over_candidate_approval_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, paper, plan_path = self._session_with_human_plan(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["verdict"] = "continue"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            self._write_ready_candidate_execution(root, paper)

            for answer in ["Do not approve the candidate.", "후보 승인하지 마."]:
                result = record_human_needed_answer(root, answer=answer, review_scope="tex_only")
                self.assertEqual(result["decision_kind"], "reject_candidate_with_reason")

    def test_answer_human_needed_reject_phrase_wins_even_with_explicit_approval_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state, paper, plan_path = self._session_with_human_plan(root)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["verdict"] = "continue"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            self._write_ready_candidate_execution(root, paper)

            result = record_human_needed_answer(
                root,
                answer="Do not approve the candidate; generate a safer revision instead.",
                intent="approve_existing_candidate",
                review_scope="tex_only",
            )

            self.assertEqual(result["decision_kind"], "reject_candidate_with_reason")
            feedback = read_json(result["feedback_path"])
            self.assertEqual(feedback["intent"], "reject_candidate_with_reason")

    def test_import_and_apply_preserve_answer_metadata_without_raw_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            result = record_human_needed_answer(
                root,
                answer=f"Weaken this claim. {PRIVATE_PHRASE}",
                intent="generate_new_operator_candidate",
            )
            imported_path, imported = import_operator_feedback(
                root,
                packet_path=result["packet_path"],
                feedback_path=result["feedback_path"],
            )
            self.assertIn("human_needed_answer", imported)
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(imported))

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nA scoped contribution paragraph.\n\\end{document}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            quality_eval = {"session_id": load_session(root).session_id, "mode": "draft", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_figure_placement_review", return_value=(root / "figure.json", {"manuscript_sha256": "sha256:test"})):
                            with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                    with patch("paperorchestra.operator_feedback.write_rendered_reference_audit", return_value=root / "rendered.json"):
                                        with patch("paperorchestra.operator_feedback.write_citation_integrity_audit", return_value=root / "integrity.json"):
                                            with patch("paperorchestra.operator_feedback.write_citation_integrity_critic", return_value=root / "critic.json"):
                                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                                        _execution_path, execution = apply_operator_feedback(
                                                            root,
                                                            MockProvider(),
                                                            imported_feedback_path=imported_path,
                                                            quality_mode="draft",
                                                        )

            self.assertIn("human_needed_answer", execution)
            self.assertEqual(execution["human_needed_answer"]["answer_sha256"], result["answer_sha256"])
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(execution))
            incorporation = read_json(execution["incorporation_report"])
            self.assertIn("human_needed_answer", incorporation)
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(incorporation))

    def test_import_rejects_inconsistent_human_needed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            result = record_human_needed_answer(
                root,
                answer="Weaken this claim.",
                intent="generate_new_operator_candidate",
            )
            feedback = read_json(result["feedback_path"])

            cases = [
                ("packet_file_sha256", "0" * 64, "packet_file_sha256"),
                ("decision_kind", "reject_candidate_with_reason", "decision_kind"),
                ("target_action_id", "not-in-packet", "target_action_id"),
                ("handoff_type", "candidate_approval", "candidate_approval"),
                ("private_answer", PRIVATE_PHRASE, "unsupported fields"),
            ]
            for key, value, message in cases:
                mutated = json.loads(json.dumps(feedback))
                mutated["human_needed_answer"][key] = value
                feedback_path = root / f"feedback-{key}.json"
                feedback_path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.subTest(key=key):
                    with self.assertRaisesRegex(ContractError, message):
                        import_operator_feedback(
                            root,
                            packet_path=result["packet_path"],
                            feedback_path=feedback_path,
                        )

            mutated = json.loads(json.dumps(feedback))
            issue = mutated["issues"][0]
            issue["source_artifact_role"] = "paper_full_tex"
            issue["source_item_key"] = "body"
            issue["id"] = derive_operator_issue_id(
                mutated["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            feedback_path = root / "feedback-selected-source-mismatch.json"
            feedback_path.write_text(json.dumps(mutated), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "selected_handoff_source"):
                import_operator_feedback(
                    root,
                    packet_path=result["packet_path"],
                    feedback_path=feedback_path,
                )

    def _feedback_with_operator_notes(self, root: Path, notes: dict) -> tuple[Path, dict, Path]:
        self._session_with_human_plan(root)
        packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
        issue_id = derive_operator_issue_id(
            packet["packet_sha256"],
            source_artifact_role="qa_loop_plan",
            source_item_key="verdict:human_needed",
            target_section="Whole manuscript",
            rationale="Manual cycle found unresolved citation and narrative issues.",
            suggested_action="Generate a bounded operator-feedback candidate that addresses the unresolved issues.",
        )
        feedback_path = root / "operator-feedback.json"
        feedback_path.write_text(
            json.dumps(
                {
                    "schema_version": "operator-feedback/1",
                    "source": "codex_operator",
                    "not_independent_human_review": True,
                    "intent": "generate_new_operator_candidate",
                    "packet_sha256": packet["packet_sha256"],
                    "manuscript_sha256": packet["manuscript_sha256"],
                    "issues": [
                        {
                            "id": issue_id,
                            "source_artifact_role": "qa_loop_plan",
                            "source_item_key": "verdict:human_needed",
                            "target_section": "Whole manuscript",
                            "severity": "major",
                            "rationale": "Manual cycle found unresolved citation and narrative issues.",
                            "suggested_action": "Generate a bounded operator-feedback candidate that addresses the unresolved issues.",
                            "authority_class": "author_feedback",
                        }
                    ],
                    "operator_review_notes": notes,
                }
            ),
            encoding="utf-8",
        )
        return packet_path, packet, feedback_path

    def test_import_operator_feedback_preserves_operator_review_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = {
                "cycle": 1,
                "trend_matrix": {
                    "narrative": "improved_but_stalled",
                    "claims": "stalled",
                    "figures": "stalled",
                    "citations": "stalled_or_regressed",
                    "benchmark_explanation": "partially_improved_but_still_needs_evidence_binding",
                },
                "pdf_attestation": "All rendered pages inspected; no layout-only blockers found.",
                "human_answer_marker": {"answer": "redacted"},
            }
            packet_path, _packet, feedback_path = self._feedback_with_operator_notes(root, notes)

            _imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            self.assertEqual(imported["operator_review_notes"], notes)

    def test_import_operator_feedback_rejects_non_object_operator_review_notes(self) -> None:
        for label, notes in (
            ("string", "plain text"),
            ("list", ["trend_matrix"]),
            ("number", 1),
            ("null", None),
        ):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    packet_path, _packet, feedback_path = self._feedback_with_operator_notes(root, notes)

                    with self.assertRaisesRegex(ContractError, "operator_review_notes"):
                        import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_import_operator_feedback_rejects_unsafe_operator_review_notes(self) -> None:
        for label, payload in FORBIDDEN_OPERATOR_NOTE_CASES:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    packet_path, _packet, feedback_path = self._feedback_with_operator_notes(root, payload)

                    with self.assertRaisesRegex(ContractError, "operator_review_notes"):
                        import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_apply_operator_feedback_revalidates_and_carries_operator_review_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = {"cycle": 1, "pdf_attestation": "All rendered pages inspected."}
            packet_path, _packet, feedback_path = self._feedback_with_operator_notes(root, notes)
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            for label, payload in FORBIDDEN_OPERATOR_NOTE_CASES:
                tampered = json.loads(json.dumps(imported))
                tampered["operator_review_notes"] = payload
                tampered_path = root / f"operator-feedback-imported-tampered-{label}.json"
                tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ContractError, "operator_review_notes"):
                        _load_imported_feedback(tampered_path)
            for label, payload in (
                ("string", "plain text"),
                ("list", ["trend_matrix"]),
                ("number", 1),
                ("null", None),
            ):
                tampered = json.loads(json.dumps(imported))
                tampered["operator_review_notes"] = payload
                tampered_path = root / f"operator-feedback-imported-tampered-nonobject-{label}.json"
                tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
                with self.subTest(label=f"non_object_{label}"):
                    with self.assertRaisesRegex(ContractError, "operator_review_notes"):
                        _load_imported_feedback(tampered_path)

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOperator notes preserved.\n\\end{document}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            quality_eval = {"session_id": load_session(root).session_id, "mode": "draft", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_figure_placement_review", return_value=(root / "figure.json", {"manuscript_sha256": "sha256:test"})):
                            with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                    with patch("paperorchestra.operator_feedback.write_rendered_reference_audit", return_value=root / "rendered.json"):
                                        with patch("paperorchestra.operator_feedback.write_citation_integrity_audit", return_value=root / "integrity.json"):
                                            with patch("paperorchestra.operator_feedback.write_citation_integrity_critic", return_value=root / "critic.json"):
                                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                                        _execution_path, execution = apply_operator_feedback(
                                                            root,
                                                            MockProvider(),
                                                            imported_feedback_path=imported_path,
                                                            quality_mode="draft",
                                                        )

            self.assertEqual(execution["operator_review_notes"], notes)
            incorporation = read_json(execution["incorporation_report"])
            self.assertEqual(incorporation["operator_review_notes"], notes)

    def test_answer_human_needed_apply_returns_public_safe_summary_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            raw_candidate = f"PRIVATE_CANDIDATE_TEXT {PRIVATE_PHRASE}"

            def fake_apply(*_args, **_kwargs):
                path = artifact_path(root, "operator_feedback.execution.json")
                payload = {
                    "verdict": "human_needed",
                    "promotion_status": "rolled_back",
                    "promotion_reason": "operator_candidate_failed_hard_gate",
                    "supervised_iteration_index": 1,
                    "supervised_remaining": 0,
                    "candidate_branch": "generate_new_operator_candidate",
                    "candidate_result": {"candidate_text": raw_candidate},
                }
                path.write_text(json.dumps(payload), encoding="utf-8")
                return path, payload

            with patch("paperorchestra.human_needed.apply_operator_feedback", side_effect=fake_apply):
                result = record_human_needed_answer(
                    root,
                    answer=f"Weaken this claim. {PRIVATE_PHRASE}",
                    intent="generate_new_operator_candidate",
                    apply=True,
                )

            self.assertIn("operator_feedback_execution_summary", result)
            self.assertNotIn("operator_feedback_execution", result)
            self.assertNotIn("imported_feedback", result)
            self.assertNotIn(raw_candidate, json.dumps(result))
            self.assertNotIn(PRIVATE_PHRASE, json.dumps(result))

    def test_cli_and_mcp_answer_human_needed_redact_raw_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session_with_human_plan(root)
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(
                        cli_main(
                            [
                                "answer-human-needed",
                                "--answer",
                                f"Weaken it. {PRIVATE_PHRASE}",
                                "--intent",
                                "generate_new_operator_candidate",
                                "--json",
                            ]
                        ),
                        0,
                    )
                payload = json.loads(stdout.getvalue())
                self.assertNotIn(PRIVATE_PHRASE, json.dumps(payload))
                self.assertEqual(payload["answer"], "redacted")

                mcp_result = TOOL_HANDLERS["answer_human_needed"](
                    {
                        "cwd": str(root),
                        "answer": f"Weaken it. {PRIVATE_PHRASE}",
                        "intent": "generate_new_operator_candidate",
                    }
                )
                self.assertFalse(mcp_result["isError"])
                self.assertNotIn(PRIVATE_PHRASE, json.dumps(mcp_result))
            finally:
                import os

                os.chdir(old_cwd)
