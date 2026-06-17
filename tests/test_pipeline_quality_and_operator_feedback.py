from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_test_support import *
from paperorchestra.fresh_smoke import normalize_operator_feedback_draft
from paperorchestra.narrative import write_planning_artifacts
from paperorchestra.operator_feedback import _attach_candidate_approval_from_attempt, _claim_safe_tier2_metric_counts


class PipelineQualityAndOperatorFeedbackTests(PipelineTestCase):
    """Quality-loop, operator-feedback, Ralph bridge, and critic-stack regression tests split out of the former PipelineTests monolith."""

    def test_normalized_operator_feedback_sanitizes_pipeline_owner_category_for_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            draft = {
                "intent": "generate_new_operator_candidate",
                "issues": [
                    {
                        "source_artifact_role": "operator_feedback_execution",
                        "source_item_key": "promotion_status:rolled_back",
                        "target_section": "Whole manuscript",
                        "severity": "blocker",
                        "rationale": "The pipeline executor did not turn valid feedback into a manuscript diff.",
                        "suggested_action": "Classify the feedback loop as an implementation issue if the executor cannot apply it.",
                        "authority_class": "author_feedback",
                        "owner_category": "pipeline",
                    }
                ],
            }

            normalized = normalize_operator_feedback_draft(packet, draft)
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps(normalized), encoding="utf-8")
            _imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            self.assertEqual(imported["issues"][0]["owner_category"], "implementation")
            self.assertEqual(imported["translated_actions"][0]["owner_category"], "implementation")

    def test_operator_candidate_approval_progress_carries_metric_issue_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.tex"
            candidate.write_text("\\documentclass{article}\n\\begin{document}\nImproved.\n\\end{document}\n", encoding="utf-8")
            execution = {"manuscript_sha256_before": "sha256:" + ("0" * 64)}
            attempt = {
                "candidate_path": str(candidate),
                "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "base_active_failures": ["citation_support_manual_check"],
                "candidate_active_failures": ["citation_support_manual_check"],
                "resolved_active_failures": ["high_risk_uncited_claim"],
                "active_tier2_metric_delta": {
                    "base_total": 9,
                    "candidate_total": 4,
                    "total_improved": True,
                    "improvements": [{"code": "citation_support_manual_check", "before": 9, "after": 4, "delta": -5}],
                },
                "verification": {"quality_eval": {"path": str(root / "quality.json")}},
            }

            _attach_candidate_approval_from_attempt(execution, attempt, execution_path=root / "operator-feedback.execution.json")

            progress = execution["candidate_progress"]
            self.assertEqual(progress["before_citation_issue_count"], 9)
            self.assertEqual(progress["after_citation_issue_count"], 4)
            self.assertEqual(progress["citation_issue_delta"], -5)
            self.assertEqual(progress["active_tier2_metric_delta"]["base_total"], 9)

    def test_operator_issue_context_protects_legacy_and_v3_untargeted_supported_citation_items(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Legacy supported fact \\cite{safeLegacy}.\n"
                "Legacy weak fact \\cite{weakLegacy}.\n"
                "Duplicate supported fact \\cite{dupKey}.\n"
                "Dense supported fact \\cite{denseKey}.\n"
                "V3 supported fact \\cite{safeV3}.\n"
                "V3 weak fact \\cite{sharedKey}.\n"
                "V3 other supported fact \\cite{sharedKey}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-support-review/3",
                        "manuscript_sha256": manuscript_sha,
                        "items": [
                            {
                                "id": "legacy-pass",
                                "citation_keys": ["safeLegacy"],
                                "sentence": "Legacy supported fact \\cite{safeLegacy}.",
                                "support_status": "supported",
                            },
                            {
                                "id": "legacy-weak",
                                "citation_keys": ["weakLegacy"],
                                "sentence": "Legacy weak fact \\cite{weakLegacy}.",
                                "support_status": "weakly_supported",
                            },
                            {
                                "id": "legacy-unsupported",
                                "citation_keys": ["unsupportedLegacy"],
                                "sentence": "Legacy unsupported fact \\cite{unsupportedLegacy}.",
                                "support_status": "unsupported",
                            },
                            {
                                "id": "legacy-supported-same-sentence",
                                "citation_keys": ["sameSentenceLegacy"],
                                "sentence": "Exact problematic shared sentence \\cite{sameSentenceLegacy}.",
                                "support_status": "supported",
                            },
                            {
                                "id": "legacy-unsupported-same-sentence",
                                "citation_keys": ["differentLegacy"],
                                "sentence": "Exact problematic shared sentence \\cite{sameSentenceLegacy}.",
                                "support_status": "unsupported",
                            },
                            {
                                "id": "legacy-dup-pass",
                                "citation_keys": ["dupKey"],
                                "sentence": "Duplicate supported fact \\cite{dupKey}.",
                                "support_status": "supported",
                            },
                            {
                                "id": "legacy-density-pass",
                                "citation_keys": ["denseKey"],
                                "sentence": "Dense supported fact \\cite{denseKey}.",
                                "support_status": "supported",
                            },
                        ],
                        "cases": [
                            {
                                "id": "C-safe-v3",
                                "key": "safeV3",
                                "anchor": "V3 supported fact \\cite{safeV3}.",
                                "verdict": "pass",
                            },
                            {
                                "id": "C-weak-v3",
                                "key": "sharedKey",
                                "anchor": "V3 weak fact \\cite{sharedKey}.",
                                "verdict": "weak",
                            },
                            {
                                "id": "C-fail-v3",
                                "key": "failKey",
                                "anchor": "V3 failed fact \\cite{failKey}.",
                                "verdict": "fail",
                            },
                            {
                                "id": "C-human-v3",
                                "key": "humanKey",
                                "anchor": "V3 human-needed fact \\cite{humanKey}.",
                                "verdict": "human_needed",
                            },
                            {
                                "id": "C-exact-pass-v3",
                                "key": "exactPassKey",
                                "anchor": "Exact v3 problematic fact \\cite{exactPassKey}.",
                                "verdict": "pass",
                            },
                            {
                                "id": "C-exact-fail-v3",
                                "key": "exactFailKey",
                                "anchor": "Exact v3 problematic fact \\cite{exactPassKey}.",
                                "verdict": "fail",
                            },
                            {
                                "id": "C-shared-pass-v3",
                                "key": "sharedKey",
                                "anchor": "V3 other supported fact \\cite{sharedKey}.",
                                "verdict": "pass",
                            },
                            {
                                "id": "C-target-fallback-v3",
                                "key": "targetOnlyKey",
                                "target": "V3 target fallback fact \\cite{targetOnlyKey}.",
                                "verdict": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "citation_integrity.audit.json").write_text(
                json.dumps(
                    {
                        "manuscript_sha256": manuscript_sha,
                        "checks": {
                            "duplicate_support": {"duplicate_keys": ["dupKey"]},
                            "citation_density": {
                                "bomb_sentences": [
                                    {
                                        "id": "density-1",
                                        "sentence": "Dense supported fact \\cite{denseKey}.",
                                        "citation_keys": ["denseKey"],
                                    }
                                ]
                            },
                        },
                        "failing_codes": ["citation_duplicate_support", "citation_bomb_detected"],
                    }
                ),
                encoding="utf-8",
            )
            self._write_terminal_human_needed_plan(root)
            packet_path, _packet = build_operator_review_packet(root, review_scope="tex_only")

            context = _operator_issue_context({"packet_path": str(packet_path)})

            protected = context["protected_supported_citation_items"]
            protected_by_id = {item["id"]: item for item in protected}
            self.assertIn("legacy-pass", protected_by_id)
            self.assertEqual(protected_by_id["legacy-pass"]["citation_keys"], ["safeLegacy"])
            self.assertEqual(protected_by_id["legacy-pass"]["sentence"], "Legacy supported fact \\cite{safeLegacy}.")
            self.assertIn("C-safe-v3", protected_by_id)
            self.assertEqual(protected_by_id["C-safe-v3"]["citation_keys"], ["safeV3"])
            self.assertEqual(protected_by_id["C-safe-v3"]["anchor"], "V3 supported fact \\cite{safeV3}.")
            self.assertIn("C-shared-pass-v3", protected_by_id)
            self.assertEqual(protected_by_id["C-shared-pass-v3"]["citation_keys"], ["sharedKey"])
            self.assertIn("C-target-fallback-v3", protected_by_id)
            self.assertEqual(protected_by_id["C-target-fallback-v3"]["citation_keys"], ["targetOnlyKey"])
            self.assertEqual(protected_by_id["C-target-fallback-v3"]["anchor"], "V3 target fallback fact \\cite{targetOnlyKey}.")
            self.assertNotIn("legacy-weak", protected_by_id)
            self.assertNotIn("legacy-unsupported", protected_by_id)
            self.assertNotIn("legacy-supported-same-sentence", protected_by_id)
            self.assertNotIn("legacy-dup-pass", protected_by_id)
            self.assertNotIn("legacy-density-pass", protected_by_id)
            self.assertNotIn("C-weak-v3", protected_by_id)
            self.assertNotIn("C-fail-v3", protected_by_id)
            self.assertNotIn("C-human-v3", protected_by_id)
            self.assertNotIn("C-exact-pass-v3", protected_by_id)
            self.assertIn("protected", context["writer_instruction"].lower())
            self.assertIn("preserve", context["writer_instruction"].lower())

    def test_operator_attempt_with_protected_citation_regression_is_not_human_review_ready(self) -> None:
        from paperorchestra.operator_feedback import _candidate_attempt_ready_for_human_review

        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.tex"
            candidate.write_text("candidate", encoding="utf-8")
            self.assertFalse(
                _candidate_attempt_ready_for_human_review(
                    {
                        "resolved_active_failures": ["high_risk_uncited_claim"],
                        "candidate_path": str(candidate),
                        "gate_reasons": ["protected_supported_citation_regression"],
                        "new_tier2_failures": [],
                    }
                )
            )

    def test_operator_feedback_rejects_candidate_that_rewrites_protected_v3_supported_citation_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            original = (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Protected source-backed fact \\cite{safeV3}.\n"
                "High-risk claim needs scope.\n"
                "\\end{document}\n"
            )
            candidate_text = (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Rewritten protected fact \\cite{safeV3}.\n"
                "Scoped repairmarker claim.\n"
                "\\end{document}\n"
            )
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-support-review/3",
                        "manuscript_sha256": manuscript_sha,
                        "cases": [
                            {
                                "id": "C-protected",
                                "key": "safeV3",
                                "anchor": "Protected source-backed fact \\cite{safeV3}.",
                                "verdict": "pass",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "manuscript_hash": "sha256:" + manuscript_sha,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["high_risk_uncited_claim"],
                                "checks": {"high_risk_claim_sweep": {"item_count": 1}},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="quality_eval",
                source_item_key="high-risk-1",
                target_section="Intro",
                rationale="High-risk claim needs scoped repairmarker wording.",
                suggested_action="Add scoped repairmarker wording without touching protected citations.",
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
                                "source_artifact_role": "quality_eval",
                                "source_item_key": "high-risk-1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "High-risk claim needs scoped repairmarker wording.",
                                "suggested_action": "Add scoped repairmarker wording without touching protected citations.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-protected-regression.tex")
            candidate.write_text(candidate_text, encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [
                    {
                        "iteration": 1,
                        "candidate_path": str(candidate),
                        "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "score_before": 70,
                        "score_after": 70,
                        "axis_scores_before": {},
                        "axis_scores_after": {},
                    }
                ]

            candidate_quality = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass", "failing_codes": [], "checks": {"high_risk_claim_sweep": {"item_count": 0}}},
                },
            }
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", candidate_quality)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        _execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            attempt = execution["attempts"][-1]
            self.assertIn("protected_supported_citation_regression", attempt["gate_reasons"])
            self.assertEqual(attempt["protected_supported_citation_regressions"][0]["id"], "C-protected")
            self.assertEqual(attempt["protected_supported_citation_regressions"][0]["citation_keys"], ["safeV3"])
            protected_attempt_evidence = json.dumps(attempt["protected_supported_citation_regressions"])
            self.assertNotIn("sentence", protected_attempt_evidence)
            self.assertNotIn("anchor", protected_attempt_evidence)
            self.assertNotIn("Protected source-backed fact", protected_attempt_evidence)
            self.assertNotIn("Protected source-backed fact", json.dumps(execution["actionable_failure"]))
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertNotIn("Protected source-backed fact", json.dumps(incorporation["actionable_failure"]))
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn("Protected source-backed fact", json.dumps(history[-1]["actionable_failure"]))
            self.assertEqual(paper.read_text(encoding="utf-8"), original)


    def test_operator_feedback_checks_protected_citation_regression_beyond_prompt_context_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            protected_cases = []
            original_lines = []
            candidate_lines = []
            for index in range(1, 27):
                key = f"safeKey{index}"
                anchor = f"Protected fact {index} \\cite{{{key}}}."
                protected_cases.append({"id": f"C-protected-{index:02d}", "key": key, "anchor": anchor, "verdict": "pass"})
                original_lines.append(anchor)
                candidate_lines.append(anchor)
            candidate_lines[-1] = "Rewritten late protected fact \\cite{safeKey26}."
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n" + "\n".join(original_lines) + "\nHigh-risk claim needs scope.\n\\end{document}\n"
            candidate_text = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n" + "\n".join(candidate_lines) + "\nScoped repairmarker claim.\n\\end{document}\n"
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps({"schema": "citation-support-review/3", "manuscript_sha256": manuscript_sha, "cases": protected_cases}),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "manuscript_hash": "sha256:" + manuscript_sha,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["high_risk_uncited_claim"],
                                "checks": {"high_risk_claim_sweep": {"item_count": 1}},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="quality_eval",
                source_item_key="high-risk-late",
                target_section="Intro",
                rationale="High-risk claim needs scoped repairmarker wording.",
                suggested_action="Add scoped repairmarker wording without touching protected citations.",
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
                                "source_artifact_role": "quality_eval",
                                "source_item_key": "high-risk-late",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "High-risk claim needs scoped repairmarker wording.",
                                "suggested_action": "Add scoped repairmarker wording without touching protected citations.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-late-protected-regression.tex")
            candidate.write_text(candidate_text, encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [
                    {
                        "iteration": 1,
                        "candidate_path": str(candidate),
                        "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "score_before": 70,
                        "score_after": 70,
                        "axis_scores_before": {},
                        "axis_scores_after": {},
                    }
                ]

            candidate_quality = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass", "failing_codes": [], "checks": {"high_risk_claim_sweep": {"item_count": 0}}},
                },
            }
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", candidate_quality)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        _execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            attempt = execution["attempts"][-1]
            self.assertIn("protected_supported_citation_regression", attempt["gate_reasons"])
            ids = {item["id"] for item in attempt["protected_supported_citation_regressions"]}
            self.assertIn("C-protected-26", ids)
            self.assertEqual(attempt["protected_supported_citation_regression_count"], 1)
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_operator_feedback_allows_rewriting_duplicate_target_supported_citation_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            original = (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Duplicate target fact \\cite{dupKey}.\n"
                "High-risk claim needs scope.\n"
                "\\end{document}\n"
            )
            candidate_text = (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Duplicate target fact rewritten without the repeated citation.\n"
                "Scoped repairmarker claim.\n"
                "\\end{document}\n"
            )
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-support-review/3",
                        "manuscript_sha256": manuscript_sha,
                        "cases": [
                            {
                                "id": "C-duplicate-target",
                                "key": "dupKey",
                                "anchor": "Duplicate target fact \\cite{dupKey}.",
                                "verdict": "pass",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "citation_integrity.audit.json").write_text(
                json.dumps(
                    {
                        "manuscript_sha256": manuscript_sha,
                        "checks": {"duplicate_support": {"duplicate_keys": ["dupKey"]}},
                        "failing_codes": ["citation_duplicate_support"],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "manuscript_hash": "sha256:" + manuscript_sha,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_duplicate_support"],
                                "checks": {"citation_quality_gate": {"counts": {"duplicate_reference_count": 1}}},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="citation_integrity_audit",
                source_item_key="duplicate:dupKey",
                target_section="Intro",
                rationale="Duplicate citation support needs scoped repairmarker wording.",
                suggested_action="Remove redundant duplicate support with scoped repairmarker wording.",
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
                                "source_artifact_role": "citation_integrity_audit",
                                "source_item_key": "duplicate:dupKey",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "Duplicate citation support needs scoped repairmarker wording.",
                                "suggested_action": "Remove redundant duplicate support with scoped repairmarker wording.",
                                "authority_class": "citation_support",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-duplicate-target.tex")
            candidate.write_text(candidate_text, encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [
                    {
                        "iteration": 1,
                        "candidate_path": str(candidate),
                        "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "score_before": 70,
                        "score_after": 70,
                        "axis_scores_before": {},
                        "axis_scores_after": {},
                    }
                ]

            candidate_quality = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {
                        "status": "pass",
                        "failing_codes": [],
                        "checks": {"citation_quality_gate": {"counts": {"duplicate_reference_count": 0}}},
                    },
                },
            }
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", candidate_quality)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        _execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertNotIn("protected_supported_citation_regression", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(paper.read_text(encoding="utf-8"), candidate_text)

    def test_qa_loop_plan_surfaces_citation_integrity_density_failures(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_integrity_gate": {
                            "status": "fail",
                            "failing_codes": [
                                "citation_bomb_detected",
                                "citation_integrity_audit_fail",
                                "citation_integrity_failed",
                            ],
                            "citation_integrity_audit": {"path": "/tmp/citation_integrity.audit.json"},
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        density_actions = [action for action in actions if action.get("code") == "citation_density_policy_failed"]
        self.assertEqual(len(density_actions), 1)
        self.assertEqual(density_actions[0]["automation"], "semi_auto")
        self.assertEqual(density_actions[0]["approval_required_from"], "citation_integrity_critic")
        self.assertIn("dense citation bundles", density_actions[0]["ralph_instruction"])

    def test_qa_loop_plan_surfaces_duplicate_support_as_executable_repair(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_integrity_gate": {
                            "status": "fail",
                            "failing_codes": ["citation_duplicate_support"],
                            "citation_integrity_audit": {"path": "/tmp/citation_integrity.audit.json"},
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        density_actions = [action for action in actions if action.get("code") == "citation_density_policy_failed"]
        self.assertEqual(len(density_actions), 1)
        self.assertEqual(density_actions[0]["automation"], "semi_auto")
        self.assertEqual(density_actions[0]["approval_required_from"], "citation_integrity_critic")
        self.assertIn("repeated support", density_actions[0]["ralph_instruction"])

    def test_qa_loop_plan_surfaces_figure_grounding_failures_as_human_needed(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "figure_grounding": {
                            "status": "fail",
                            "path": "/tmp/figure-placement-review.json",
                            "failing_codes": [
                                "nontechnical_visual_asset_in_body",
                                "figure_caption_plot_purpose_mismatch",
                            ],
                            "figures": [
                                {
                                    "label": "fig:latency",
                                    "section_title": "Results",
                                    "failing_codes": ["figure_caption_plot_purpose_mismatch"],
                                    "included_assets": ["fig_latency_breakdown.tex"],
                                    "nearby_reference_context": "Figure compares latency across workloads.",
                                    "plot_manifest_match": {"title": "Latency breakdown", "purpose": "Compare latency."},
                                },
                                {
                                    "label": "fig:bio",
                                    "section_title": "Background",
                                    "failing_codes": ["nontechnical_visual_asset_in_body"],
                                },
                            ],
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        figure_actions = [action for action in actions if str(action.get("code")).startswith("figure_") or action.get("code") == "nontechnical_visual_asset_in_body"]
        self.assertEqual({action["code"] for action in figure_actions}, {"nontechnical_visual_asset_in_body", "figure_caption_plot_purpose_mismatch"})
        self.assertTrue(all(action["automation"] == "human_needed" for action in figure_actions))
        self.assertTrue(all(action["approval_required_from"] == "figure_placement_review_critic" for action in figure_actions))
        latency_action = next(action for action in figure_actions if action["code"] == "figure_caption_plot_purpose_mismatch")
        self.assertIn("fig:latency", latency_action["target"])
        self.assertIn("fig_latency_breakdown.tex", latency_action["reason"])
        self.assertIn("Compare latency", latency_action["reason"])
        verdict, reason = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)
        self.assertEqual(verdict, "human_needed")
        self.assertIn("human", reason)

    def test_unsafe_figure_codes_are_not_supported_automatic_handlers(self) -> None:
        from paperorchestra.quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES

        unsafe_codes = {
            "nontechnical_visual_asset_in_body",
            "figure_caption_process_or_placeholder",
            "figure_reference_context_missing",
            "figure_caption_plot_purpose_mismatch",
        }

        self.assertTrue(unsafe_codes.isdisjoint(QA_LOOP_SUPPORTED_HANDLER_CODES))

    def test_selected_section_plot_context_filter_preserves_referenced_figures(self) -> None:
        section_text = (
            "\\section{Results}\n"
            "Figure~\\cref{fig:latency} compares latency across workloads.\n"
            "\\begin{figure}[t]\n"
            "\\input{fig_latency_breakdown.tex}\n"
            "\\caption{Latency breakdown across workloads.}\n"
            "\\label{fig:latency}\n"
            "\\end{figure}\n"
        )
        manifest = {
            "figures": [
                {"figure_id": "fig:latency", "title": "Latency breakdown"},
                {"figure_id": "fig:memory", "title": "Memory footprint"},
            ]
        }
        assets = {
            "assets": [
                {"figure_id": "fig:latency", "latex_snippet_path": "fig_latency_breakdown.tex"},
                {"figure_id": "fig:memory", "latex_snippet_path": "fig_memory.tex"},
            ]
        }

        scoped_manifest, scoped_assets = _filter_plot_context_for_latex(section_text, manifest, assets)

        self.assertEqual([item["figure_id"] for item in scoped_manifest["figures"]], ["fig:latency"])
        self.assertEqual([item["figure_id"] for item in scoped_assets["assets"]], ["fig:latency"])

    def test_selected_section_plot_context_filter_handles_multi_cref_and_normalized_ids(self) -> None:
        section_text = "\\section{Results}\nFigure~\\cref{fig:latency-breakdown,fig:memory} compares both views.\n"
        manifest = {
            "figures": [
                {"figure_id": "fig_latency_breakdown", "title": "Latency breakdown"},
                {"figure_id": "fig:memory", "title": "Memory footprint"},
            ]
        }
        assets = {
            "assets": [
                {"figure_id": "fig_latency_breakdown", "latex_snippet_path": "fig_latency_breakdown.tex"},
                {"figure_id": "fig:memory", "latex_snippet_path": "fig_memory.tex"},
            ]
        }

        scoped_manifest, scoped_assets = _filter_plot_context_for_latex(section_text, manifest, assets)

        self.assertEqual({item["figure_id"] for item in scoped_manifest["figures"]}, {"fig_latency_breakdown", "fig:memory"})
        self.assertEqual({item["figure_id"] for item in scoped_assets["assets"]}, {"fig_latency_breakdown", "fig:memory"})

    def test_qa_loop_plan_continues_for_supported_citation_density_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Dense claim~\\cite{A,B,C,D}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            citation_support = artifact_path(root, "citation_support_review.json")
            citation_support.write_text(json.dumps({"items": []}), encoding="utf-8")
            quality_eval_path = artifact_path(root, "quality-eval.synthetic.json")
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "cross_iteration": {
                            "budget": {"remaining": 5, "current_attempt_consumes_budget": False},
                            "regression": {"forward_progress": True},
                        },
                        "source_artifacts": {"citation_review_sha256": hashlib.sha256(citation_support.read_bytes()).hexdigest()},
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass", "failing_codes": []},
                            "tier_1_structural": {"status": "pass", "failing_codes": []},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_bomb_detected"],
                                "checks": {
                                    "citation_integrity_gate": {
                                        "status": "fail",
                                        "failing_codes": ["citation_bomb_detected", "citation_integrity_failed"],
                                        "citation_integrity_audit": {"path": str(artifact_path(root, "citation_integrity.audit.json"))},
                                    }
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("paperorchestra.quality_loop.run_fidelity_audit", return_value={"overall_status": "pass"}):
                with patch("paperorchestra.quality_loop.write_reproducibility_audit", return_value=artifact_path(root, "reproducibility.audit.json")):
                    with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value={"verdict": "PASS", "citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1}):
                        _, plan = write_quality_loop_plan(
                            root,
                            quality_mode="claim_safe",
                            quality_eval_input_path=quality_eval_path,
                            append_history=False,
                        )

            self.assertEqual(plan["verdict"], "continue")
            self.assertIn("executable action citation_density_policy_failed", plan["next_ralph_instruction"])
            self.assertEqual(plan["quality_eval_summary"]["tier_statuses"]["tier_2_claim_safety"], "fail")
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")

    def test_qa_loop_plan_continues_for_supported_citation_coverage_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSparse citation coverage.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            citation_support = artifact_path(root, "citation_support_review.json")
            citation_support.write_text(json.dumps({"items": []}), encoding="utf-8")
            validation_report = artifact_path(root, "validation.coverage.json")
            validation_report.write_text(
                json.dumps(
                    {
                        "stage": "refinement",
                        "issues": [
                            {
                                "code": "citation_coverage_insufficient",
                                "severity": "error",
                                "message": "Insufficient citation coverage.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            quality_eval_path = artifact_path(root, "quality-eval.coverage.json")
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "cross_iteration": {
                            "budget": {"remaining": 5, "current_attempt_consumes_budget": False},
                            "regression": {"forward_progress": True},
                        },
                        "source_artifacts": {"citation_review_sha256": hashlib.sha256(citation_support.read_bytes()).hexdigest()},
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass", "failing_codes": []},
                            "tier_1_structural": {"status": "pass", "failing_codes": []},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_coverage_insufficient"],
                                "checks": {},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            reproducibility = {
                "verdict": "PASS",
                "citation_artifact_issues": [],
                "strict_content_gate_issues": [],
                "prompt_trace_file_count": 1,
                "validation_warning_reports": [{"path": str(validation_report)}],
            }
            with patch("paperorchestra.quality_loop.run_fidelity_audit", return_value={"overall_status": "pass"}):
                with patch("paperorchestra.quality_loop.write_reproducibility_audit", return_value=artifact_path(root, "reproducibility.audit.json")):
                    with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility):
                        _, plan = write_quality_loop_plan(
                            root,
                            quality_mode="claim_safe",
                            quality_eval_input_path=quality_eval_path,
                            append_history=False,
                        )

            coverage_actions = [action for action in plan["repair_actions"] if action.get("code") == "citation_coverage_insufficient"]
            self.assertEqual(plan["verdict"], "continue")
            self.assertEqual(len(coverage_actions), 1)
            self.assertEqual(coverage_actions[0]["automation"], "semi_auto")
            self.assertIn("executable action citation_coverage_insufficient", plan["next_ralph_instruction"])

    def test_qa_loop_plan_continues_for_high_risk_uncited_claim_repair(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "high_risk_claim_sweep": {
                            "status": "fail",
                            "failing_codes": ["high_risk_uncited_claim"],
                            "items": [
                                {
                                    "line": 7,
                                    "sentence": "The system eliminates all failures in realistic deployments.",
                                    "reason": "high-risk claim lacks citation or scoped limitation",
                                }
                            ],
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        high_risk_actions = [action for action in actions if action.get("code") == "high_risk_uncited_claim"]
        self.assertEqual(len(high_risk_actions), 1)
        self.assertEqual(high_risk_actions[0]["automation"], "semi_auto")
        self.assertIn("existing verified evidence", high_risk_actions[0]["ralph_instruction"])
        self.assertEqual(high_risk_actions[0]["approval_required_from"], "claim_safety_critic")

    def test_operator_tier2_metrics_include_weak_reference_identity_counts(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_quality_gate": {
                            "counts": {
                                "critical_weak_identity_count": 2,
                                "noncritical_weak_identity_count": 3,
                            }
                        }
                    }
                }
            }
        }

        metrics = _claim_safe_tier2_metric_counts(quality_eval)

        self.assertEqual(metrics["critical_weak_reference_identity"], 2)
        self.assertEqual(metrics["noncritical_weak_reference_identity"], 3)

    def test_operator_tier2_metrics_read_internal_cqg_counts_not_public_report(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_quality_gate": {
                            "status": "fail",
                            "hard_gate_failures": ["critical_unsupported_citation"],
                            "counts": {
                                "critical_unsupported_count": 1,
                                "critical_need_count": 2,
                                "critical_weak_identity_count": 3,
                                "noncritical_weak_identity_count": 4,
                                "citation_bomb_count": 5,
                                "duplicate_reference_count": 6,
                            },
                            "public_report": {
                                "schema": "citation-quality-gate/2",
                                "status": "fail",
                                "summary": {"pass": 0, "weak": 0, "fail": 0, "human_needed": 1},
                                "failures": [{"case": "C1", "key": "Known", "code": "human_needed", "message": "Source required."}],
                            },
                        }
                    }
                }
            }
        }

        metrics = _claim_safe_tier2_metric_counts(quality_eval)

        self.assertEqual(metrics["critical_unsupported_citation"], 1)
        self.assertEqual(metrics["critical_citation_support_missing"], 2)
        self.assertEqual(metrics["critical_weak_reference_identity"], 3)
        self.assertEqual(metrics["noncritical_weak_reference_identity"], 4)
        self.assertEqual(metrics["citation_bomb_detected"], 5)
        self.assertEqual(metrics["citation_duplicate_support"], 6)

    def test_qa_loop_step_attempts_citation_integrity_repair_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDense~\\cite{A,B,C,D}.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_bomb_detected"]}},
            }
            after_eval = {
                **before_eval,
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_bomb_detected"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_density_policy_failed", "automation": "semi_auto"}],
            }
            plan_after = {**plan, "verdict": "human_needed"}
            validation_path = root / "validation.citation-repair.json"
            validation_path.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "blocking_issue_count": 1,
                        "issues": [{"code": "citation_coverage_insufficient"}],
                    }
                ),
                encoding="utf-8",
            )
            repair_payload = {
                "accepted": False,
                "reason": "validation_failed",
                "issue_count": 1,
                "validation": {"path": str(validation_path), "ok": False, "blocking_issue_count": 1},
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", plan_after)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload) as repair:
                            with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                    with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json"):
                                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "fail", "failing_codes": ["citation_bomb_detected"]}):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            repair.assert_called_once()
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "citation_density_policy_failed")
            self.assertEqual(attempted[0]["handler"], "repair_citation_claims")
            failure = result.payload["repair_failures"][0]
            self.assertEqual(failure["reason"], "validation_failed")
            self.assertEqual(failure["validation"]["failing_codes"], ["citation_coverage_insufficient"])
            self.assertEqual(result.payload["actionable_failure"]["category"], "citation_repair_failed")
            self.assertEqual(result.payload["actionable_failure"]["validation_failing_codes"], ["citation_coverage_insufficient"])
            self.assertNotEqual(result.payload["verdict"], "ready_for_human_finalization")

    def test_qa_loop_step_attempts_citation_coverage_repair_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSparse citation coverage.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_coverage_insufficient"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_coverage_insufficient", "automation": "semi_auto"}],
            }
            plan_after = {**plan, "verdict": "human_needed"}
            validation_path = root / "validation.citation-coverage.json"
            validation_path.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "blocking_issue_count": 1,
                        "issues": [{"code": "citation_coverage_insufficient"}],
                    }
                ),
                encoding="utf-8",
            )
            repair_payload = {
                "accepted": False,
                "reason": "validation_failed",
                "issue_count": 1,
                "validation": {"path": str(validation_path), "ok": False, "blocking_issue_count": 1},
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", before_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", plan_after)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload) as repair:
                            with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                    with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json"):
                                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "fail"}):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            repair.assert_called_once()
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "citation_coverage_insufficient")
            self.assertEqual(attempted[0]["handler"], "repair_citation_claims")
            self.assertEqual(result.payload.get("actions_skipped"), [])

    def test_candidate_semantic_recheck_uses_bound_full_high_risk_baseline(self) -> None:
        from paperorchestra.ralph_bridge_repair import _candidate_semantic_recheck

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\nOriginal claim.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            original_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "manuscript_hash": "sha256:" + original_hash,
                        "tiers": {
                            "tier_2_claim_safety": {
                                "checks": {
                                    "high_risk_claim_sweep": {
                                        "status": "fail",
                                        "failing_codes": ["high_risk_uncited_claim"],
                                        "item_count": 20,
                                        "items": [{} for _ in range(20)],
                                    }
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            paper.write_text(original.replace("Original", "Candidate"), encoding="utf-8")
            issues = [{"issue_type": "high_risk_uncited_claim", "sentence": f"issue {i}"} for i in range(16)]
            with patch("paperorchestra.ralph_bridge_repair.build_citation_integrity_audit", return_value={"status": "pass", "failing_codes": [], "checks": {}}):
                with patch("paperorchestra.ralph_bridge_repair.evaluate_source_obligations", return_value={}):
                    with patch("paperorchestra.ralph_bridge_repair._high_risk_claim_sweep", return_value={"status": "fail", "failing_codes": ["high_risk_uncited_claim"], "item_count": 18, "items": [{} for _ in range(18)]}):
                        result = _candidate_semantic_recheck(root, claim_safety_issues=issues, original_manuscript_hash=original_hash)

            high_risk = result["high_risk_claim_sweep"]
            self.assertEqual(result["status"], "pass")
            self.assertEqual(high_risk["baseline_source"], "quality_eval")
            self.assertEqual(high_risk["before"]["item_count"], 20)
            self.assertEqual(high_risk["after"]["item_count"], 18)
            self.assertTrue(high_risk["improved"])

    def test_candidate_semantic_recheck_ignores_stale_high_risk_baseline(self) -> None:
        from paperorchestra.ralph_bridge_repair import _candidate_semantic_recheck

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\nOriginal claim.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            original_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "manuscript_hash": "sha256:stale",
                        "tiers": {
                            "tier_2_claim_safety": {
                                "checks": {
                                    "high_risk_claim_sweep": {
                                        "status": "fail",
                                        "failing_codes": ["high_risk_uncited_claim"],
                                        "item_count": 20,
                                    }
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            paper.write_text(original.replace("Original", "Candidate"), encoding="utf-8")
            issues = [{"issue_type": "high_risk_uncited_claim", "sentence": f"issue {i}"} for i in range(16)]
            with patch("paperorchestra.ralph_bridge_repair.build_citation_integrity_audit", return_value={"status": "pass", "failing_codes": [], "checks": {}}):
                with patch("paperorchestra.ralph_bridge_repair.evaluate_source_obligations", return_value={}):
                    with patch("paperorchestra.ralph_bridge_repair._high_risk_claim_sweep", return_value={"status": "fail", "failing_codes": ["high_risk_uncited_claim"], "item_count": 18, "items": [{} for _ in range(18)]}):
                        result = _candidate_semantic_recheck(root, claim_safety_issues=issues, original_manuscript_hash=original_hash)

            high_risk = result["high_risk_claim_sweep"]
            self.assertEqual(result["status"], "fail")
            self.assertEqual(high_risk["baseline_source"], "quality_eval_stale_ignored")
            self.assertEqual(high_risk["before"]["item_count"], 16)
            self.assertEqual(high_risk["after"]["item_count"], 18)
            self.assertFalse(high_risk["improved"])

    def test_citation_repair_failure_payload_summarizes_semantic_recheck(self) -> None:
        from paperorchestra.ralph_bridge import _citation_repair_failure_payload

        repair = {
            "reason": "semantic_recheck_failed",
            "issue_count": 2,
            "claim_safety_issue_count": 1,
            "candidate_path": "/tmp/private-candidate-with-text.tex",
            "validation": {"ok": True, "blocking_issue_count": 0},
            "semantic_recheck": {
                "status": "fail",
                "citation_integrity": {
                    "targeted": True,
                    "improved": False,
                    "path": "/tmp/citation-integrity.json",
                    "sha256": "sha256:citation",
                    "before": {"target_issue_count": 3, "other_detail": "do not copy"},
                    "after": {"target_issue_count": 3},
                },
                "high_risk_claim_sweep": {
                    "targeted": True,
                    "improved": True,
                    "path": "/tmp/high-risk.json",
                    "sha256": "sha256:highrisk",
                    "before": {"item_count": 2},
                    "after": {"item_count": 0},
                },
            },
        }

        failure = _citation_repair_failure_payload("citation_support_critic_failed", repair)

        self.assertEqual(failure["reason"], "semantic_recheck_failed")
        self.assertEqual(failure["semantic_recheck_blockers"], ["citation_integrity_not_improved"])
        citation = failure["semantic_recheck"]["citation_integrity"]
        self.assertTrue(citation["targeted"])
        self.assertFalse(citation["improved"])
        self.assertEqual(citation["before_count"], 3)
        self.assertEqual(citation["after_count"], 3)
        high_risk = failure["semantic_recheck"]["high_risk_claim_sweep"]
        self.assertTrue(high_risk["improved"])
        self.assertEqual(high_risk["before_count"], 2)
        self.assertEqual(high_risk["after_count"], 0)
        self.assertIn("semantic_recheck blockers", failure["next_steps"][0])
        self.assertNotIn("do not copy", json.dumps(failure))

    def test_qa_loop_step_actionable_failure_includes_semantic_recheck_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nClaim~\\cite{A}.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_critic_failed"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            repair_payload = {
                "accepted": False,
                "reason": "semantic_recheck_failed",
                "issue_count": 1,
                "claim_safety_issue_count": 1,
                "validation": {"ok": True, "blocking_issue_count": 0},
                "semantic_recheck": {
                    "status": "fail",
                    "citation_integrity": {
                        "targeted": True,
                        "improved": False,
                        "before": {"target_issue_count": 2},
                        "after": {"target_issue_count": 2},
                    },
                    "high_risk_claim_sweep": {
                        "targeted": False,
                        "improved": True,
                        "before": {"item_count": 0},
                        "after": {"item_count": 0},
                    },
                },
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "before.json", before_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan-before.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload):
                            result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            failure = result.payload["actionable_failure"]
            self.assertEqual(failure["category"], "citation_repair_failed")
            self.assertEqual(failure["reason"], "semantic_recheck_failed")
            self.assertEqual(failure["semantic_recheck_blockers"], ["citation_integrity_not_improved"])
            self.assertEqual(result.payload["repair_failures"][0]["semantic_recheck_blockers"], ["citation_integrity_not_improved"])
            self.assertNotIn("Claim~", json.dumps(failure))

    def test_qa_loop_step_routes_critical_citation_quality_to_refresh_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Claim~\\cite{Unknown}.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["critical_unsupported_citation"]}},
            }
            after_eval = {
                **before_eval,
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["critical_unsupported_citation"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "critical_unsupported_citation", "automation": "semi_auto"}],
            }
            plan_after = {**plan, "verdict": "human_needed"}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", plan_after)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json") as review:
                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "fail", "failing_codes": ["critical_unsupported_citation"]}) as refresh:
                                with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                    with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                        with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                            result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertGreaterEqual(review.call_count, 1)
            self.assertGreaterEqual(refresh.call_count, 1)
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "critical_unsupported_citation")
            self.assertEqual(attempted[0]["handler"], "refresh_citation_quality")
            self.assertEqual(result.payload.get("actions_skipped"), [])

    def test_qa_loop_step_routes_weak_reference_identity_with_non_destructive_bib_rebuild_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Critical source needs traceable metadata~\\cite{WeakIdentity}.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["critical_weak_reference_identity"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "critical_weak_reference_identity", "automation": "semi_auto"}],
            }
            plan_after = {**plan, "verdict": "human_needed"}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", before_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", plan_after)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.build_bib", side_effect=ContractError("Run verify-papers before build-bib."), create=True) as rebuild:
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json") as review:
                                with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "fail", "failing_codes": ["critical_weak_reference_identity"]}) as refresh:
                                    with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                        with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                            with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            rebuild.assert_called_once()
            self.assertGreaterEqual(review.call_count, 1)
            self.assertGreaterEqual(refresh.call_count, 1)
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "critical_weak_reference_identity")
            self.assertEqual(attempted[0]["handler"], "refresh_citation_quality")
            self.assertFalse(attempted[0]["bibtex_rebuild"]["ok"])
            self.assertIn("Run verify-papers before build-bib", attempted[0]["bibtex_rebuild"]["error"])
            self.assertEqual(result.payload.get("actions_skipped"), [])

    def test_qa_loop_step_refreshes_unbound_citation_evidence_before_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nClaim~\\cite{A}.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_evidence_research_needed", "automation": "automatic"}],
            }
            after_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}},
            }
            after_plan = {**plan, "verdict": "human_needed"}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", after_plan)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims") as repair:
                            with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                    with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json") as review:
                                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "pass"}):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="web")

            repair.assert_not_called()
            review.assert_called()
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "citation_support_evidence_research_needed")
            self.assertEqual(attempted[0]["handler"], "review_citations")

    def test_qa_loop_step_refreshes_weak_unbound_citation_evidence_before_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nClaim~\\cite{A}.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_evidence_research_needed", "automation": "automatic"}],
            }
            after_eval = before_eval
            after_plan = {**plan, "verdict": "human_needed"}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before.json", before_eval), (root / "after.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "plan-before.json", plan), (root / "plan-after.json", after_plan)]):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims") as repair:
                            with patch("paperorchestra.ralph_bridge.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                                with patch("paperorchestra.ralph_bridge.write_section_review", return_value=root / "section_review.json"):
                                    with patch("paperorchestra.ralph_bridge.write_figure_placement_review", return_value=(root / "figure_review.json", {"manuscript_sha256": "x"})):
                                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json") as review:
                                            with patch("paperorchestra.ralph_bridge._refresh_citation_integrity_for_current_manuscript", return_value={"status": "pass"}):
                                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="web")

            repair.assert_not_called()
            review.assert_called()
            attempted = result.payload.get("actions_attempted", [])
            self.assertEqual(attempted[0]["code"], "citation_support_evidence_research_needed")
            self.assertEqual(attempted[0]["handler"], "review_citations")

    def test_qa_loop_plan_makes_stale_citation_integrity_refresh_executable(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_integrity_gate": {
                            "status": "fail",
                            "failing_codes": ["citation_integrity_stale"],
                            "citation_integrity_audit": {"path": "/tmp/citation_integrity.audit.json"},
                        }
                    },
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)

        refresh_actions = [action for action in actions if action.get("code") == "citation_integrity_stale"]
        self.assertEqual(len(refresh_actions), 1)
        self.assertEqual(refresh_actions[0]["automation"], "automatic")
        from paperorchestra.quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES

        self.assertIn("citation_integrity_stale", QA_LOOP_SUPPORTED_HANDLER_CODES)

    def test_operator_issue_context_includes_citation_density_issues_from_packet(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Dense claim~\\cite{A,B,C,D}.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            audit_path = artifact_path(root, "citation_integrity.audit.json")
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-audit/1",
                        "status": "fail",
                        "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "failing_codes": ["citation_bomb_detected"],
                        "checks": {
                            "citation_density": {
                                "status": "fail",
                                "bomb_sentences": [
                                    {
                                        "id": "tex-sentence-1",
                                        "sentence": "Dense claim~\\cite{A,B,C,D}.",
                                        "citation_keys": ["A", "B", "C", "D"],
                                    }
                                ],
                                "bomb_paragraph_key_sets": [["A", "B", "C", "D", "E", "F"]],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            critic_path = artifact_path(root, "citation_integrity.critic.json")
            critic_path.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-critic/1",
                        "status": "fail",
                        "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "reviewed_artifacts": [],
                        "failing_codes": ["citation_bomb_detected"],
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            context = _operator_issue_context({"packet_path": str(packet_path)})

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("citation_integrity_audit", roles)
            self.assertIn("citation_integrity_critic", roles)
            density = context["citation_density_issues"]
            self.assertEqual(density[0]["issue_type"], "citation_bomb_sentence")
            self.assertEqual(density[0]["citation_count"], 4)
            self.assertEqual(density[1]["issue_type"], "citation_bomb_paragraph")
            self.assertEqual(density[1]["citation_count"], 6)
            constraints = context["refinement_constraints"]
            self.assertIn("citation_bomb_detected", constraints["before_failing_codes"])
            self.assertIn("citation_support_weak", constraints["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_manual_check", constraints["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_unsupported", constraints["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_insufficient_evidence", constraints["forbidden_new_tier2_codes"])
            self.assertTrue(any("Do not use dense citation bundles to hide weak support" in item for item in constraints["hard_constraints"]))

    def test_operator_issue_context_ignores_missing_citation_density_artifact(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, _ = build_operator_review_packet(root, review_scope="tex_only")

            context = _operator_issue_context({"packet_path": str(packet_path)})

            self.assertNotIn("citation_density_issues", context)

    def test_operator_issue_context_includes_bounded_prior_rejection_memory(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, _ = build_operator_review_packet(root, review_scope="tex_only")
            prior_attempts = [
                {
                    "attempt_index": 1,
                    "candidate_path": "/tmp/should-not-leak.tex",
                    "candidate_sha256": "sha256:abc",
                    "gate_passed": False,
                    "gate_reasons": ["active_tier2_metric_regression"],
                    "base_active_failures": ["citation_support_manual_check"],
                    "candidate_active_failures": ["citation_support_manual_check"],
                    "resolved_active_failures": ["citation_support_weak"],
                    "new_tier2_failures": [],
                    "active_tier2_metric_delta": {
                        "regressions": [{"code": "citation_support_manual_check", "before": 3, "after": 4, "delta": 1}],
                        "improvements": [{"code": "citation_support_weak", "before": 5, "after": 2, "delta": -3}],
                        "base_total": 8,
                        "candidate_total": 6,
                    },
                },
                {"attempt_index": 2, "gate_passed": True, "candidate_sha256": "sha256:promoted"},
            ]

            context = _operator_issue_context({"packet_path": str(packet_path)}, prior_attempts=prior_attempts)

            memory = context["prior_rejected_attempts"]
            self.assertEqual(len(memory), 1)
            self.assertEqual(memory[0]["attempt_index"], 1)
            self.assertEqual(memory[0]["candidate_sha256"], "sha256:abc")
            self.assertEqual(memory[0]["gate_reasons"], ["active_tier2_metric_regression"])
            self.assertEqual(memory[0]["metric_regressions"][0]["code"], "citation_support_manual_check")
            self.assertEqual(memory[0]["metric_improvements"][0]["code"], "citation_support_weak")
            self.assertNotIn("candidate_path", memory[0])
            self.assertIn("do not repeat", context["prior_rejection_instruction"].lower())

    def test_qa_loop_plan_supervised_handoff_uses_canonical_packet_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")
            plan["verdict"] = "human_needed"
            plan["repair_actions"] = [{"code": "missing_prompt_trace", "automation": "human_needed"}]
            plan_path = artifact_path(root, "qa-loop.plan.json")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            entry = plan["supervised_handoff"]["operator_feedback_entry"]
            self.assertEqual(entry["packet_path"], str(packet_path))
            self.assertEqual(entry["packet_sha256"], packet["packet_sha256"])
            self.assertNotEqual(entry["packet_sha256"], __import__("hashlib").sha256(Path(packet_path).read_bytes()).hexdigest())

    def test_operator_feedback_public_surfaces_are_explicit_only(self) -> None:
        cli_parser = cli_main.__globals__["build_parser"]()
        cli_commands = set(cli_parser._subparsers._group_actions[0].choices)
        self.assertTrue(OPERATOR_PUBLIC_ENTRYPOINTS.issubset(cli_commands))
        self.assertFalse({"operator-feedback", "write-operator-feedback", "author-operator-feedback"} & cli_commands)

        mcp_names = {tool["name"] for tool in MCP_TOOLS}
        self.assertTrue({"build_operator_review_packet", "import_operator_feedback", "apply_operator_feedback"}.issubset(mcp_names))
        self.assertIn("critique", mcp_names)
        self.assertIn("suggest_revisions", mcp_names)
        self.assertIn("refine_current_paper", mcp_names)
        self.assertIn("build_operator_review_packet", TOOL_HANDLERS)
        self.assertIn("import_operator_feedback", TOOL_HANDLERS)
        self.assertIn("apply_operator_feedback", TOOL_HANDLERS)

    def test_qa_loop_bridge_exit_codes_and_progress_delta(self) -> None:
        self.assertEqual(qa_loop_exit_code("ready_for_human_finalization"), 0)
        self.assertEqual(qa_loop_exit_code("continue"), 10)
        self.assertEqual(qa_loop_exit_code("human_needed"), 20)
        self.assertEqual(qa_loop_exit_code("failed"), 30)
        self.assertEqual(qa_loop_exit_code("unknown"), 40)

        before = {"manuscript_hash": "sha256:before", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        after = {"manuscript_hash": "sha256:after", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        delta = compute_progress_delta(before, after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertTrue(delta["forward_progress"])
        self.assertEqual(delta["resolved_codes"], ["citation_support_unsupported"])
        self.assertEqual(delta["citation_issue_delta"], -2)

        same_before = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported", "citation_support_weak"]}}}
        same_after = {"manuscript_hash": "sha256:same", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}}
        same_delta = compute_progress_delta(same_before, same_after, {"unsupported": 1, "weakly_supported": 2}, {"weakly_supported": 1})
        self.assertFalse(same_delta["forward_progress"])
        self.assertTrue(same_delta["same_manuscript_as_previous"])
        unknown_delta = compute_progress_delta(
            {"tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}}},
            {"tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}}},
            {"weakly_supported": 1},
            {"supported": 1},
        )
        self.assertFalse(unknown_delta["manuscript_identity_known"])
        self.assertFalse(unknown_delta["forward_progress"])

    def test_quality_loop_cross_iteration_blocks_same_manuscript_failure_drift_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".paper-orchestra"
            runtime.mkdir()
            (runtime / "qa-loop-history.jsonl").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "event_type": "qa_loop_step",
                        "consumes_budget": True,
                        "manuscript_hash": "sha256:same",
                        "failing_codes": ["citation_support_unsupported", "citation_support_weak"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            cross = _build_cross_iteration(
                root,
                "s1",
                "sha256:same",
                ["citation_support_weak"],
                10,
                current_attempt_consumes_budget=True,
            )
            self.assertTrue(cross["regression"]["same_manuscript_as_previous"])
            self.assertFalse(cross["regression"]["forward_progress"])

    def test_quality_loop_cross_iteration_detects_repeated_actionable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".paper-orchestra"
            runtime.mkdir()
            failure = {
                "category": "citation_repair_failed",
                "code": "citation_support_critic_failed",
                "reason": "validation_failed",
                "validation_failing_codes": ["citation_coverage_insufficient"],
            }
            (runtime / "qa-loop-history.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "session_id": "s1",
                            "event_type": "qa_loop_step",
                            "consumes_budget": True,
                            "manuscript_hash": f"sha256:{idx}",
                            "failing_codes": ["citation_support_weak"],
                            "actionable_failure": failure,
                        }
                    )
                    for idx in range(2)
                )
                + "\n",
                encoding="utf-8",
            )

            cross = _build_cross_iteration(root, "s1", "sha256:current", ["citation_support_weak"], 10)

            repeated = cross["regression"]["repeated_actionable_failure"]
            self.assertTrue(repeated["detected"])
            self.assertEqual(repeated["count"], 2)
            self.assertEqual(repeated["signature"], failure)

    def test_quality_loop_cross_iteration_single_actionable_failure_does_not_escalate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".paper-orchestra"
            runtime.mkdir()
            (runtime / "qa-loop-history.jsonl").write_text(
                json.dumps(
                    {
                        "session_id": "s1",
                        "event_type": "qa_loop_step",
                        "consumes_budget": True,
                        "manuscript_hash": "sha256:one",
                        "failing_codes": ["citation_support_weak"],
                        "actionable_failure": {
                            "category": "citation_repair_failed",
                            "code": "citation_support_critic_failed",
                            "reason": "validation_failed",
                            "validation_failing_codes": ["citation_coverage_insufficient"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            cross = _build_cross_iteration(root, "s1", "sha256:current", ["citation_support_weak"], 10)

            self.assertFalse(cross["regression"]["repeated_actionable_failure"]["detected"])

    def test_citation_support_review_reuses_same_session_web_review(self) -> None:
        class CountingCitationProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                ids = ["cite-001"]
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item_id,
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item_id in ids
                        ],
                        "research_notes": ["synthetic stable evidence"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = CountingCitationProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_text = first.read_text(encoding="utf-8")
            second = write_citation_support_review(root, provider=provider, evidence_mode="web")

            self.assertEqual(provider.call_count, 2)
            self.assertEqual(second.read_text(encoding="utf-8"), first_text)
            payload = json.loads(second.read_text(encoding="utf-8"))
            provenance = payload["evidence_provenance"]
            self.assertEqual(provenance["cache_scope"], "session_id")
            self.assertIn("cache_key_sha256", provenance)
            self.assertIn("retrieved_web_evidence_sha256", provenance)
            self.assertEqual(provenance["evidence_identity_source"], "pre_review_retrieved_evidence_artifact")
            retrieved_evidence_path = Path(provenance["retrieved_web_evidence_path"])
            self.assertTrue(retrieved_evidence_path.exists())

            original_cache_key = provenance["cache_key_sha256"]
            retrieved_payload = json.loads(retrieved_evidence_path.read_text(encoding="utf-8"))
            retrieved_payload["research_notes"] = ["synthetic changed retrieved evidence"]
            retrieved_evidence_path.write_text(json.dumps(retrieved_payload, indent=2), encoding="utf-8")
            changed_evidence = write_citation_support_review(root, provider=provider, evidence_mode="web")
            changed_provenance = json.loads(changed_evidence.read_text(encoding="utf-8"))["evidence_provenance"]
            self.assertEqual(provider.call_count, 3)
            self.assertNotEqual(changed_provenance["cache_key_sha256"], original_cache_key)

            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\nChanged synthetic claim. \\cite{A}\n\\end{document}\n",
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 5)

            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source Changed", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            write_citation_support_review(root, provider=provider, evidence_mode="web")
            self.assertEqual(provider.call_count, 7)

    def test_web_citation_evidence_retrieval_is_chunked_for_large_claim_sets(self) -> None:
        class ChunkObservingProvider(MockProvider):
            def __init__(self) -> None:
                self.retrieval_chunk_sizes: list[int] = []
                self.review_calls = 0

            def _input_items(self, request: CompletionRequest) -> list[dict[str, Any]]:
                marker = "Input:\n"
                payload = request.user_prompt.split(marker, 1)[1]
                if "\n\nA separate pre-review" in payload:
                    payload = payload.split("\n\nA separate pre-review", 1)[0]
                return json.loads(payload)["items"]

            def complete(self, request: CompletionRequest) -> str:
                items = self._input_items(request)
                if "citation-support evidence retriever" in request.system_prompt:
                    self.retrieval_chunk_sizes.append(len(items))
                    return json.dumps(
                        {
                            "items": [
                                {
                                    "id": item["id"],
                                    "evidence": [
                                        {
                                            "citation_key": item["citation_keys"][0],
                                            "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                            "url": f"https://example.test/{item['citation_keys'][0]}",
                                            "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                                for item in items
                            ],
                            "research_notes": ["chunked synthetic retrieval"],
                        }
                    )
                self.review_calls += 1
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": item["id"],
                                "support_status": "supported",
                                "risk": "low",
                                "claim_type": item.get("claim_type") or "background",
                                "evidence": [
                                    {
                                        "citation_key": item["citation_keys"][0],
                                        "source_title": f"Synthetic Source {item['citation_keys'][0]}",
                                        "url": f"https://example.test/{item['citation_keys'][0]}",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": True,
                                    }
                                ],
                                "reasoning": "Synthetic cited source directly supports the claim.",
                                "suggested_fix": "",
                            }
                            for item in items
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                + "\n".join(f"Synthetic claim {i}. \\cite{{A{i}}}" for i in range(1, 10))
                + "\n\\end{document}\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        f"A{i}": {
                            "title": f"Synthetic Source A{i}",
                            "url": f"https://example.test/A{i}",
                            "authors": ["A. Author"],
                            "year": 2026,
                        }
                        for i in range(1, 10)
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider = ChunkObservingProvider()
            path = write_citation_support_review(root, provider=provider, evidence_mode="web")
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(provider.retrieval_chunk_sizes, [8, 1])
            self.assertEqual(provider.review_calls, 1)
            self.assertEqual(payload["summary"], {"supported": 9})
            retrieved_path = Path(payload["evidence_provenance"]["retrieved_web_evidence_path"])
            self.assertTrue(_retrieved_web_evidence_is_reusable(json.loads(retrieved_path.read_text(encoding="utf-8"))))

    def test_malformed_web_retrieval_is_not_cached_as_citation_review(self) -> None:
        class FlakyRetrievalProvider(MockProvider):
            def __init__(self) -> None:
                self.call_count = 0

            def complete(self, request: CompletionRequest) -> str:
                self.call_count += 1
                if "citation-support evidence retriever" in request.system_prompt:
                    if self.call_count == 1:
                        return '{"items": ['
                    return json.dumps(
                        {
                            "items": [
                                {
                                    "id": "cite-001",
                                    "evidence": [
                                        {
                                            "citation_key": "A",
                                            "source_title": "Synthetic Source",
                                            "url": "https://example.test/source",
                                            "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                            ],
                            "research_notes": ["valid retry retrieval"],
                        }
                    )
                status = "needs_manual_check" if self.call_count == 2 else "supported"
                return json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": status,
                                "risk": "medium" if status == "needs_manual_check" else "low",
                                "claim_type": "background",
                                "evidence": [
                                    {
                                        "citation_key": "A",
                                        "source_title": "Synthetic Source",
                                        "url": "https://example.test/source",
                                        "evidence_quote_or_summary": "Synthetic source directly supports the synthetic claim.",
                                        "supports_claim": status == "supported",
                                    }
                                ],
                                "reasoning": "Synthetic review.",
                                "suggested_fix": "",
                            }
                        ],
                        "research_notes": ["synthetic review"],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"A": {"title": "Synthetic Source", "url": "https://example.test/source", "authors": ["A. Author"], "year": 2026}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            provider = FlakyRetrievalProvider()

            first = write_citation_support_review(root, provider=provider, evidence_mode="web")
            first_payload = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 2)
            self.assertNotIn("cache_key_sha256", first_payload["evidence_provenance"])

            second = write_citation_support_review(root, provider=provider, evidence_mode="web")
            second_payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(provider.call_count, 4)
            self.assertEqual(second_payload["summary"], {"supported": 1})
            self.assertIn("cache_key_sha256", second_payload["evidence_provenance"])

    def test_retrieved_web_evidence_reusability_allows_some_metadata_only_items(self) -> None:
        self.assertTrue(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": [{"citation_key": "A"}]},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [
                        {"id": "cite-001", "evidence": []},
                        {"id": "cite-002", "evidence": []},
                    ],
                    "trace": {"schema_version": "citation-support-retrieval-trace/1"},
                }
            )
        )
        self.assertFalse(
            _retrieved_web_evidence_is_reusable(
                {
                    "items": [{"id": "cite-001", "evidence": [{"citation_key": "A"}]}],
                    "trace": {
                        "schema_version": "citation-support-retrieval-trace/1",
                        "chunk_traces": [{"parse_error": "JSONDecodeError"}],
                    },
                }
            )
        )

    def test_citation_support_cache_key_includes_shell_provider_command_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic claim. \\cite{A}\n\\end{document}\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"A": {"title": "Synthetic Source"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            provider_a = ShellProvider(command="codex --model gpt-a")
            provider_b = ShellProvider(command="codex --model gpt-b")
            key_a = _citation_support_cache_key(state, provider_a, "web", retrieved_web_evidence_sha256="sha256:evidence")
            key_b = _citation_support_cache_key(state, provider_b, "web", retrieved_web_evidence_sha256="sha256:evidence")

            self.assertNotEqual(key_a, key_b)

    def test_final_citation_review_must_match_quality_eval_gate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review_a = root / "citation-a.json"
            review_b = root / "citation-b.json"
            review_a.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
            review_b.write_text(json.dumps({"summary": {"unsupported": 1}}), encoding="utf-8")
            quality_eval = root / "quality-eval.json"
            quality_eval.write_text(
                json.dumps({"source_artifacts": {"citation_review_sha256": hashlib.sha256(review_b.read_bytes()).hexdigest()}}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_a)
            result = ensure_final_citation_review_bound_to_quality_eval(quality_eval, review_b)
            self.assertEqual(result["status"], "pass")

    def test_qa_loop_brief_contains_omx_handoff_and_no_success_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            brief = build_qa_loop_brief(root, quality_mode="claim_safe")

            self.assertIn("omx ralph --prd", brief)
            for verdict in ["continue", "human_needed", "ready_for_human_finalization", "failed"]:
                self.assertIn(verdict, brief)
            self.assertIn("There is no terminal state named `success`", brief)
            self.assertIn("paperorchestra qa-loop-step --quality-mode claim_safe", brief)
            self.assertIn("[OMX_TMUX_INJECT]", brief)
            self.assertIn("PAPERO_MODEL_CMD is required", brief)
            self.assertIn("## Exit code contract", brief)

    def test_qa_loop_brief_prioritizes_executable_actions_over_human_needed_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval_path = root / "quality-eval.synthetic.json"
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
                    }
                ),
                encoding="utf-8",
            )
            plan_path = root / "qa-loop.plan.synthetic.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "verdict": "continue",
                        "repair_actions": [
                            {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "reason": "Sidecar human issue."},
                            {"code": "citation_support_critic_failed", "automation": "semi_auto", "reason": "Executable citation repair."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            brief = build_qa_loop_brief(root, quality_eval_path=quality_eval_path, plan_path=plan_path)

            executable_section = brief.split("## Executable repair actions", 1)[1].split("## Human-needed", 1)[0]
            self.assertIn("citation_support_critic_failed", executable_section)
            self.assertNotIn("fidelity_runtime_parity_missing", executable_section)
            self.assertIn("do not stop only because separate human-needed actions are also listed", brief)

    def test_fidelity_actions_do_not_mark_unsupported_handlers_executable(self) -> None:
        from paperorchestra.quality_loop_actions import _fidelity_actions
        from paperorchestra.quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES

        actions = _fidelity_actions(
            {
                "checks": [
                    {
                        "code": "section_writing_pipeline",
                        "status": "partial",
                        "rationale": "writer lane did not complete",
                    }
                ]
            }
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["code"], "fidelity_section_writing_pipeline_partial")
        self.assertNotIn(actions[0]["code"], QA_LOOP_SUPPORTED_HANDLER_CODES)
        self.assertEqual(actions[0]["automation"], "human_needed")

    def test_fidelity_actions_distinguish_missing_from_recorded_partial_runtime_parity(self) -> None:
        from paperorchestra.quality_loop_actions import _fidelity_actions

        implemented_actions = _fidelity_actions(
            {
                "checks": [
                    {"code": "compile_environment_ready", "status": "implemented", "rationale": "ready"},
                    {"code": "runtime_parity", "status": "implemented", "rationale": "all lanes recorded"},
                ]
            }
        )
        self.assertEqual(implemented_actions, [])

        partial_actions = _fidelity_actions(
            {
                "checks": [
                    {"code": "compile_environment_ready", "status": "implemented", "rationale": "ready"},
                    {"code": "runtime_parity", "status": "partial", "rationale": "refinement lane is absent"},
                ]
            }
        )

        codes = {action.get("code") for action in partial_actions}
        self.assertIn("fidelity_runtime_parity_partial", codes)
        self.assertNotIn("fidelity_runtime_parity_missing", codes)

    def test_next_ralph_instruction_uses_supported_executable_action(self) -> None:
        instruction = _next_ralph_instruction(
            "continue",
            [
                {"code": "fidelity_runtime_parity_missing", "automation": "human_needed", "ralph_instruction": "Ask a human."},
                {
                    "code": "citation_support_critic_failed",
                    "automation": "semi_auto",
                    "ralph_instruction": "Repair cited claims.",
                    "suggested_commands": ["paperorchestra repair-citation-claims"],
                },
            ],
        )

        self.assertIn("executable action citation_support_critic_failed", instruction)
        self.assertIn("Repair cited claims", instruction)
        self.assertNotIn("Ask a human", instruction)

    def test_repair_citation_claims_softens_sentence_and_rejects_unknown_citation(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "QUIC is always faster than every transport~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC is always faster than every transport~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Soften the claim to a source-supported protocol statement.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )
            repaired_latex = original.replace(
                "QUIC is always faster than every transport~\\cite{RFC9001}.",
                "RFC 9001 describes how TLS is used to secure QUIC~\\cite{RFC9001}.",
            )
            provider = RepairProvider(repaired_latex)

            result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertTrue(result["accepted"])
            self.assertFalse(result["committed"])
            self.assertIn("citation_support_issues.json", provider.prompt)
            self.assertNotIn("overall_score", provider.prompt)
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))
            self.assertIn("TLS is used to secure QUIC", Path(result["candidate_path"]).read_text(encoding="utf-8"))

            bad_provider = RepairProvider(repaired_latex.replace("\\cite{RFC9001}", "\\cite{FakeNew}"))
            paper.write_text(original, encoding="utf-8")
            bad_result = repair_citation_claims(root, bad_provider, citation_review_path=review_path)
            self.assertFalse(bad_result["accepted"])
            self.assertEqual(bad_result["reason"], "unknown_citation_keys")
            self.assertIn("QUIC is always faster", paper.read_text(encoding="utf-8"))

    def test_repair_citation_claims_prompt_includes_density_and_high_risk_issue_context(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RefA,title={A},year={2020}}\n"
                "@article{RefB,title={B},year={2020}}\n"
                "@article{RefC,title={C},year={2020}}\n"
                "@article{RefD,title={D},year={2020}}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "Background context is over-cited~\\cite{RefA,RefB,RefC,RefD}.\n"
                "The method demonstrates invariant-preservation claim with a 2.5x measured improvement.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            obligations_path = artifact_path(root, "source_obligations.json")
            from paperorchestra.source_obligations import build_source_obligations

            packet_sha = build_source_obligations(root)["source_packet_sha256"]
            obligations_path.write_text(
                json.dumps(
                    {
                        "schema_version": "source-obligations/1",
                        "source_packet_sha256": packet_sha,
                        "obligations": [
                            {
                                "id": "obl-001-theorem_or_bound",
                                "type": "theorem_or_bound",
                                "expected_manuscript_area": "security_analysis",
                                "required_terms": ["construction", "proves", "invariant-preservation", "security"],
                                "numeric_tokens": ["2.5x"],
                                "excerpt_preview": "The author-provided material claims invariant-preservation claim and a 2.5x result.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.source_obligations_json = str(obligations_path)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(json.dumps({"items": [], "summary": {}}), encoding="utf-8")
            from paperorchestra.citation_integrity import write_citation_integrity_audit
            from paperorchestra.quality_loop_source_checks import _high_risk_claim_sweep

            write_citation_integrity_audit(root, quality_mode="claim_safe")
            sweep = _high_risk_claim_sweep(load_session(root), {"status": "fail", "path": str(artifact_path(root, "source_obligations.json"))})
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "tiers": {
                            "tier_2_claim_safety": {
                                "checks": {
                                    "high_risk_claim_sweep": sweep,
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            provider = RepairProvider(original)

            repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertIn("claim_safety_repair_issues.json", provider.prompt)
            self.assertIn("source_obligations_context.json", provider.prompt)
            self.assertIn("invariant-preservation", provider.prompt)
            self.assertIn("2.5x", provider.prompt)
            self.assertIn("citation_bomb_sentence", provider.prompt)
            self.assertIn("high_risk_uncited_claim", provider.prompt)
            self.assertIn("invariant-preservation claim", provider.prompt)
            self.assertIn("required_action", provider.prompt)

    def test_source_obligation_repair_context_rejects_stale_or_legacy_matrices(self) -> None:
        from paperorchestra.ralph_bridge_repair import _source_obligation_repair_context
        from paperorchestra.source_obligations import build_source_obligations

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "The method reports a 2.5x benchmark result.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            obligations_path = artifact_path(root, "source_obligations.json")
            stale_payload = {
                "schema_version": "source-obligations/1",
                "source_packet_sha256": "stale",
                "obligations": [
                    {
                        "id": "obl-stale",
                        "type": "benchmark_result",
                        "required_terms": ["stale-private-term"],
                        "numeric_tokens": ["2.5x"],
                        "excerpt_preview": "stale-private-term must never be injected",
                    }
                ],
            }
            obligations_path.write_text(json.dumps(stale_payload), encoding="utf-8")
            state.artifacts.source_obligations_json = str(obligations_path)
            save_session(root, state)

            stale_context = _source_obligation_repair_context(root)
            self.assertFalse(stale_context["available"])
            self.assertEqual(stale_context["reason"], "source_obligations_stale")
            self.assertNotIn("stale-private-term", json.dumps(stale_context))

            current_packet_sha = build_source_obligations(root)["source_packet_sha256"]
            legacy_payload = dict(stale_payload)
            legacy_payload["schema_version"] = "legacy"
            legacy_payload["source_packet_sha256"] = current_packet_sha
            obligations_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

            legacy_context = _source_obligation_repair_context(root)
            self.assertFalse(legacy_context["available"])
            self.assertEqual(legacy_context["reason"], "source_obligations_legacy_untrusted")
            self.assertNotIn("stale-private-term", json.dumps(legacy_context))

    def test_repair_citation_claims_prompt_includes_duplicate_support_issue_context(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text("@article{RefA,title={A},year={2020}}\n", encoding="utf-8")
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "Repeated background claim one~\\cite{RefA}.\n"
                "Repeated background claim two~\\cite{RefA}.\n"
                "Repeated background claim three~\\cite{RefA}.\n"
                "Repeated background claim four~\\cite{RefA}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": f"support-{index}",
                                "sentence": f"Repeated background claim {index}.",
                                "citation_keys": ["RefA"],
                                "support_status": "supported",
                            }
                            for index in range(1, 5)
                        ],
                        "summary": {"supported": 4},
                    }
                ),
                encoding="utf-8",
            )
            from paperorchestra.citation_integrity import write_citation_integrity_audit

            write_citation_integrity_audit(root, quality_mode="claim_safe")
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps({"tiers": {"tier_2_claim_safety": {"checks": {"high_risk_claim_sweep": {"items": []}}}}}),
                encoding="utf-8",
            )
            provider = RepairProvider(original)

            validation_path = artifact_path(root, "validation.citation-repair.json")
            with patch(
                "paperorchestra.ralph_bridge_repair.record_current_validation_report",
                return_value=(validation_path, {"ok": True, "blocking_issue_count": 0}),
            ):
                result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "semantic_recheck_failed")
            self.assertIn("claim_safety_repair_issues.json", provider.prompt)
            self.assertIn("citation_duplicate_support", provider.prompt)
            self.assertIn("RefA", provider.prompt)
            self.assertIn("affected_items", provider.prompt)
            self.assertNotIn("citation_bomb_sentence", provider.prompt)
            self.assertNotIn("high_risk_uncited_claim", provider.prompt)
            self.assertGreater(result["semantic_recheck"]["citation_integrity"]["before"]["duplicate_support_count"], 0)
            self.assertGreater(result["semantic_recheck"]["citation_integrity"]["after"]["duplicate_support_count"], 0)

    def test_repair_citation_claims_accepts_improved_candidate_with_candidate_scoped_rechecks(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RefA,title={A},year={2020}}\n"
                "@article{RefB,title={B},year={2020}}\n"
                "@article{RefC,title={C},year={2020}}\n"
                "@article{RefD,title={D},year={2020}}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "Background context is over-cited~\\cite{RefA,RefB,RefC,RefD}.\n"
                "The method demonstrates invariant-preservation claim with a 2.5x measured improvement.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            candidate = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "The current draft does not claim security, benchmark improvement, or general performance superiority.\n"
                "Prior work is cited as background~\\cite{RefA}. Additional context is separated~\\cite{RefB}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(json.dumps({"items": [], "summary": {}}), encoding="utf-8")
            from paperorchestra.citation_integrity import write_citation_integrity_audit
            from paperorchestra.quality_loop_source_checks import _high_risk_claim_sweep

            canonical_citation_path, _ = write_citation_integrity_audit(root, quality_mode="claim_safe")
            canonical_citation_before = canonical_citation_path.read_text(encoding="utf-8")
            sweep = _high_risk_claim_sweep(load_session(root), {"status": "fail", "path": str(artifact_path(root, "source_obligations.json"))})
            quality_eval_path = artifact_path(root, "quality-eval.json")
            quality_eval_payload = {
                "tiers": {"tier_2_claim_safety": {"checks": {"high_risk_claim_sweep": sweep}}},
            }
            quality_eval_path.write_text(json.dumps(quality_eval_payload), encoding="utf-8")
            state = load_session(root)
            state.artifacts.latest_validation_json = str(artifact_path(root, "validation.before.json"))
            Path(state.artifacts.latest_validation_json).write_text(json.dumps({"ok": True}), encoding="utf-8")
            save_session(root, state)
            before_pointer = load_session(root).artifacts.latest_validation_json
            provider = RepairProvider(candidate)

            validation_path = artifact_path(root, "validation.citation-repair.json")
            with patch(
                "paperorchestra.ralph_bridge_repair.record_current_validation_report",
                return_value=(validation_path, {"ok": True, "blocking_issue_count": 0}),
            ):
                result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertTrue(result["accepted"])
            self.assertFalse(result["committed"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            self.assertEqual(load_session(root).artifacts.latest_validation_json, before_pointer)
            self.assertEqual(canonical_citation_path.read_text(encoding="utf-8"), canonical_citation_before)
            self.assertEqual(json.loads(quality_eval_path.read_text(encoding="utf-8")), quality_eval_payload)
            semantic = result["semantic_recheck"]
            self.assertEqual(semantic["status"], "pass")
            self.assertTrue(Path(semantic["citation_integrity"]["path"]).exists())
            self.assertTrue(Path(semantic["high_risk_claim_sweep"]["path"]).exists())
            self.assertLess(semantic["citation_integrity"]["after"]["citation_bomb_sentence_count"], semantic["citation_integrity"]["before"]["citation_bomb_sentence_count"])
            self.assertLess(semantic["high_risk_claim_sweep"]["after"]["item_count"], semantic["high_risk_claim_sweep"]["before"]["item_count"])

    def test_repair_citation_claims_rejects_candidate_without_semantic_improvement(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RefA,title={A},year={2020}}\n"
                "@article{RefB,title={B},year={2020}}\n"
                "@article{RefC,title={C},year={2020}}\n"
                "@article{RefD,title={D},year={2020}}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\n"
                "Background context is over-cited~\\cite{RefA,RefB,RefC,RefD}.\n"
                "The method demonstrates invariant-preservation claim with a 2.5x measured improvement.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                "\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(json.dumps({"items": [], "summary": {}}), encoding="utf-8")
            from paperorchestra.citation_integrity import write_citation_integrity_audit
            from paperorchestra.quality_loop_source_checks import _high_risk_claim_sweep

            canonical_citation_path, _ = write_citation_integrity_audit(root, quality_mode="claim_safe")
            canonical_citation_before = canonical_citation_path.read_text(encoding="utf-8")
            sweep = _high_risk_claim_sweep(load_session(root), {"status": "fail", "path": str(artifact_path(root, "source_obligations.json"))})
            quality_eval_path = artifact_path(root, "quality-eval.json")
            quality_eval_payload = {"tiers": {"tier_2_claim_safety": {"checks": {"high_risk_claim_sweep": sweep}}}}
            quality_eval_path.write_text(json.dumps(quality_eval_payload), encoding="utf-8")
            provider = RepairProvider(original)

            validation_path = artifact_path(root, "validation.citation-repair.json")
            with patch(
                "paperorchestra.ralph_bridge_repair.record_current_validation_report",
                return_value=(validation_path, {"ok": True, "blocking_issue_count": 0}),
            ):
                result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "semantic_recheck_failed")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            self.assertEqual(canonical_citation_path.read_text(encoding="utf-8"), canonical_citation_before)
            self.assertEqual(json.loads(quality_eval_path.read_text(encoding="utf-8")), quality_eval_payload)
            self.assertEqual(result["semantic_recheck"]["status"], "fail")

    def test_repair_citation_claims_restores_state_when_semantic_recheck_errors(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text("@techreport{RFC9001,title={Using TLS to Secure QUIC},year={2021}}\n", encoding="utf-8")
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC is always faster than every transport~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            candidate = original.replace(
                "QUIC is always faster than every transport~\\cite{RFC9001}.",
                "RFC 9001 describes TLS use in QUIC~\\cite{RFC9001}.",
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_validation_json = str(artifact_path(root, "validation.before.json"))
            Path(state.artifacts.latest_validation_json).write_text(json.dumps({"ok": True}), encoding="utf-8")
            save_session(root, state)
            before_pointer = load_session(root).artifacts.latest_validation_json
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC is always faster than every transport~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "unsupported",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            provider = RepairProvider(candidate)
            validation_path = artifact_path(root, "validation.citation-repair.json")
            with patch(
                "paperorchestra.ralph_bridge_repair.record_current_validation_report",
                return_value=(validation_path, {"ok": True, "blocking_issue_count": 0}),
            ):
                with patch("paperorchestra.ralph_bridge_repair._candidate_semantic_recheck", side_effect=RuntimeError("boom")):
                    result = repair_citation_claims(root, provider, citation_review_path=review_path)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "semantic_recheck_error")
            self.assertEqual(result["semantic_recheck"]["status"], "error")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            self.assertEqual(load_session(root).artifacts.latest_validation_json, before_pointer)

    def test_ralph_start_dry_run_cli_does_not_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", side_effect=AssertionError("should not launch")):
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--dry-run", "--max-iterations", "5", "--require-live-verification"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"]["status"], "dry_run")
            self.assertIn("omx ralph --prd", payload["suggested_command"])
            self.assertIn("--max-iterations 5", payload["argv"][3])
            self.assertEqual(payload["schema_version"], "paperorchestra-ralph-handoff/1")
            self.assertEqual(payload["hook_contract"]["marker"], "[OMX_TMUX_INJECT]")
            self.assertEqual(payload["hook_contract"]["continuation_exit_code"], 10)
            self.assertTrue(payload["execution_contract"]["require_live_verification"])
            self.assertTrue(payload["execution_contract"]["ralph_required"])
            self.assertTrue(payload["execution_contract"]["critic_required"])
            self.assertTrue(payload["execution_contract"]["citation_integrity_gate_required"])
            self.assertEqual(payload["execution_contract"]["human_needed_cycle_policy"]["requested_cycles"], 5)
            self.assertIn("PAPERO_MODEL_CMD", payload["execution_contract"]["step_command"])
            self.assertTrue(Path(payload["handoff_path"]).exists())
            self.assertTrue(Path(payload["canonical_prd_path"]).exists())
            self.assertTrue(Path(payload["canonical_test_spec_path"]).exists())
            self.assertTrue(Path(payload["prd_path"]).exists())
            prd = json.loads(Path(payload["prd_path"]).read_text(encoding="utf-8"))
            self.assertEqual(prd["project"], "PaperOrchestra Ralph QA Loop")

    def test_claim_safe_quality_eval_requires_citation_integrity_and_critic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            registry = artifact_path(root, "citation_registry.json")
            registry.write_text(json.dumps([{"paper_id": "rfc9001", "title": "Using TLS to Secure QUIC", "year": 2021, "venue": "RFC", "authors": ["Martin Thomson", "Sean Turner"], "bibtex_key": "RFC9001"}]), encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC", "paper_id": "rfc9001", "year": 2021, "url": "https://www.rfc-editor.org/rfc/rfc9001"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            state.artifacts.citation_registry_json = str(registry)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            state = load_session(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report = artifact_path(root, "compile-report.json")
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility), patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            tier2 = quality_eval["tiers"].get("tier_2_claim_safety", {})
            failing = set(tier2.get("failing_codes") or [])
            self.assertIn("citation_integrity_missing", failing)
            self.assertIn("citation_critic_missing", failing)
            self.assertIn("ralph_handoff_missing", failing)
            checks = tier2["checks"]["citation_integrity_gate"]
            self.assertEqual(checks["status"], "fail")
            self.assertIn("citation_integrity_audit", quality_eval["source_artifacts"])
            self.assertIn("citation_integrity_critic", quality_eval["source_artifacts"])
            self.assertIn("ralph_handoff", quality_eval["source_artifacts"])

    def test_claim_safe_quality_eval_accepts_bound_citation_integrity_critic_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{RFC9001} Using TLS to Secure QUIC.\n", encoding="utf-8")
            support = paper.parent / "citation_support_review.json"
            support.write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "supported",
                                "evidence": [{"url": "https://www.rfc-editor.org/rfc/rfc9001"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            state = load_session(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report = artifact_path(root, "compile-report.json")
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)

            from paperorchestra.citation_integrity import (
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility), patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            checks = quality_eval["tiers"]["tier_2_claim_safety"]["checks"]["citation_integrity_gate"]
            self.assertEqual(checks["status"], "pass")
            for key in [
                "rendered_reference_audit",
                "citation_intent_plan",
                "citation_source_match",
                "citation_integrity_audit",
                "citation_integrity_critic",
            ]:
                self.assertIn(key, quality_eval["source_artifacts"])
                self.assertTrue(quality_eval["source_artifacts"].get(f"{key}_sha256"))

    def test_claim_safe_citation_integrity_artifacts_must_be_bound_to_current_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}Body.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            from paperorchestra.citation_integrity import citation_integrity_check, citation_integrity_audit_path, citation_integrity_critic_path, rendered_reference_audit_path

            for path in [citation_integrity_audit_path(root), citation_integrity_critic_path(root), rendered_reference_audit_path(root)]:
                path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            unbound = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")
            self.assertIn("citation_integrity_unbound", unbound["failing_codes"])
            self.assertIn("citation_critic_unbound", unbound["failing_codes"])
            self.assertIn("rendered_reference_audit_unbound", unbound["failing_codes"])

            wrong = "sha256:not-current"
            for path in [citation_integrity_audit_path(root), citation_integrity_critic_path(root), rendered_reference_audit_path(root)]:
                path.write_text(json.dumps({"status": "pass", "manuscript_sha256": wrong}), encoding="utf-8")
            stale = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")
            self.assertIn("citation_integrity_stale", stale["failing_codes"])
            self.assertIn("citation_critic_stale", stale["failing_codes"])
            self.assertIn("rendered_reference_audit_stale", stale["failing_codes"])

    def test_ralph_start_launch_calls_omx_ralph_explicitly(self) -> None:
        class FakeProc:
            pid = 4242

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stdout = io.StringIO()
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                with patch("paperorchestra.cli.launch_omx_ralph", return_value=FakeProc()) as launcher:
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(["ralph-start", "--launch"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["launch"], {"pid": 4242, "status": "started"})
            argv = launcher.call_args.args[0]
            self.assertEqual(argv[:3], ["omx", "ralph", "--prd"])
            self.assertIn("PaperOrchestra Ralph Brief", argv[3])

    def test_qa_loop_planning_surfaces_do_not_consume_execution_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            for _ in range(5):
                write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
                build_qa_loop_brief(root, quality_mode="claim_safe", max_iterations=5)
                build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5)

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(history), 5)
            self.assertTrue(all(entry["event_type"] == "qa_loop_plan" for entry in history))
            self.assertTrue(all(entry["consumes_budget"] is False for entry in history))

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 0)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 5)
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe", max_iterations=5)
            self.assertNotEqual(plan["verdict"], "failed")

    def test_quality_loop_budget_is_session_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "session_id": "po-other",
                            "event_type": "qa_loop_step",
                            "consumes_budget": True,
                            "manuscript_hash": "sha256:other",
                            "failing_codes": ["citation_support_weak"],
                        }
                    )
                    for _ in range(7)
                )
                + "\n",
                encoding="utf-8",
            )
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)

            budget = quality_eval["cross_iteration"]["budget"]
            self.assertEqual(quality_eval["session_id"], state.session_id)
            self.assertEqual(budget["attempts_used"], 0)
            self.assertEqual(budget["remaining"], 5)
            self.assertEqual(quality_eval["cross_iteration"]["iteration_index"], 1)

    def test_quality_loop_plan_stops_after_budgeted_no_progress_with_supported_repairs(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_weak"],
                }
            },
            "cross_iteration": {
                "budget": {
                    "remaining": 3,
                    "current_attempt_consumes_budget": True,
                },
                "regression": {
                    "forward_progress": False,
                    "oscillation": {"detected": False, "flapping_codes": []},
                    "tier_3_axis_drops": [],
                },
            },
        }
        actions = [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "human_needed")
        self.assertIn("no forward progress", rationale)

        quality_eval["cross_iteration"]["budget"]["current_attempt_consumes_budget"] = False
        verdict, _ = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)
        self.assertEqual(verdict, "continue")

    def test_quality_loop_plan_stops_on_repeated_actionable_repair_failure(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_weak"],
                }
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {
                    "forward_progress": True,
                    "oscillation": {"detected": False, "flapping_codes": []},
                    "tier_3_axis_drops": [],
                    "repeated_actionable_failure": {
                        "detected": True,
                        "count": 2,
                        "signature": {
                            "category": "citation_repair_failed",
                            "code": "citation_support_critic_failed",
                            "reason": "validation_failed",
                            "validation_failing_codes": ["citation_coverage_insufficient"],
                        },
                    },
                },
            },
        }
        actions = [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "human_needed")
        self.assertIn("repeated actionable repair failure", rationale)

    def test_section_process_residue_is_non_reviewable_failure(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {
                    "status": "fail",
                    "checks": {
                        "section_quality_critic": {
                            "status": "fail",
                            "path": "section_review.json",
                            "failing_codes": ["section_process_residue_detected"],
                        }
                    },
                    "failing_codes": ["section_process_residue_detected"],
                },
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }
        actions = _quality_eval_actions(quality_eval)

        verdict, rationale = _plan_verdict(quality_eval, actions, accept_mixed_provenance=False)

        self.assertEqual(verdict, "failed")
        self.assertIn("non-reviewable", rationale)

    def test_mixed_provenance_boolean_without_acceptance_artifact_is_not_ready(self) -> None:
        quality_eval = {
            "provenance_trust": {
                "level": "mixed",
                "mixed_acceptance": {"status": "missing", "failing_codes": ["mixed_provenance_acceptance_missing"]},
            },
            "tiers": {
                "tier_0_preconditions": {"status": "pass"},
                "tier_1_structural": {"status": "pass"},
                "tier_2_claim_safety": {"status": "pass"},
                "tier_3_scholarly_quality": {"status": "pass"},
            },
            "cross_iteration": {
                "budget": {"remaining": 3, "current_attempt_consumes_budget": False},
                "regression": {"forward_progress": True, "oscillation": {"detected": False}, "tier_3_axis_drops": []},
            },
        }

        verdict, _ = _plan_verdict(quality_eval, [], accept_mixed_provenance=True)

        self.assertEqual(verdict, "human_needed")

    def test_qa_loop_actions_route_mixed_cited_provenance_to_human_acceptance(self) -> None:
        reproducibility = {
            "blocking_reasons": [
                "Live citation verification was required, but 1 cited reference has mixed cited provenance that needs explicit operator acceptance."
            ],
            "source_artifacts": {"citation_registry_json": "/tmp/session/artifacts/citation_registry.json"},
        }

        from paperorchestra.quality_loop_actions import _mode_actions

        actions = _mode_actions(reproducibility)

        mixed_actions = [action for action in actions if action.get("code") == "mixed_citation_provenance_requires_acceptance"]
        self.assertEqual(len(mixed_actions), 1)
        self.assertEqual(mixed_actions[0]["automation"], "human_needed")
        self.assertIn("mixed cited provenance", mixed_actions[0]["reason"])
        self.assertIn("explicitly accept", mixed_actions[0]["ralph_instruction"])

    def test_qa_loop_actions_keep_seed_only_citations_on_live_verification_path(self) -> None:
        reproducibility = {
            "blocking_reasons": [
                "Live citation verification was required, but 2 citation registry entries are still seed-only or curated metadata without live verification."
            ],
            "source_artifacts": {"citation_registry_json": "/tmp/session/artifacts/citation_registry.json"},
        }

        from paperorchestra.quality_loop_actions import _mode_actions

        actions = _mode_actions(reproducibility)

        seed_actions = [action for action in actions if action.get("code") == "incomplete_live_verification"]
        mixed_actions = [action for action in actions if action.get("code") == "mixed_citation_provenance_requires_acceptance"]
        self.assertEqual(len(seed_actions), 1)
        self.assertEqual(seed_actions[0]["automation"], "human_needed")
        self.assertEqual(mixed_actions, [])

    def test_provenance_trust_uses_cited_counts_not_unused_registry_entries(self) -> None:
        from paperorchestra.quality_loop import _provenance_trust

        trust = _provenance_trust(
            {
                "verdict": "OK",
                "verification_invoked": True,
                "prompt_trace_file_count": 1,
                "lane_manifest_summary": {"manifest_count": 1},
                "citation_live_provenance": {
                    "registry_count": 2,
                    "seed_only_count": 1,
                    "cited_entry_count": 1,
                    "cited_curated_seed_count": 0,
                    "cited_mixed_count": 0,
                    "status": "live",
                },
            }
        )

        self.assertEqual(trust["level"], "live")
        self.assertNotIn("citation_registry_seed_only_count=1", trust["mixed_evidence"])

    def test_provenance_trust_names_missing_registry_verification_separately_from_live_review(self) -> None:
        from paperorchestra.quality_loop import _provenance_trust

        trust = _provenance_trust(
            {
                "verdict": "OK",
                "verification_invoked": False,
                "semantic_scholar_required": False,
                "citation_support_review_live": True,
                "prompt_trace_file_count": 1,
                "lane_manifest_summary": {"manifest_count": 1},
                "citation_live_provenance": {
                    "registry_count": 0,
                    "live_verified_count": 0,
                    "seed_only_count": 0,
                    "status": "missing",
                },
            }
        )

        self.assertTrue(trust["citation_support_review_live"])
        self.assertFalse(trust["citation_registry_verification_invoked"])
        self.assertFalse(trust["semantic_scholar_required"])
        self.assertEqual(trust["citation_registry_live_verified_count"], 0)
        self.assertIn("citation_registry_live_verification_not_invoked", trust["mixed_evidence"])
        self.assertNotIn("live_verification_not_invoked", trust["mixed_evidence"])

    def test_reproducibility_audit_records_live_citation_support_review_separately(self) -> None:
        from paperorchestra.fidelity import build_reproducibility_audit

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nBackground~\\cite{A}.\n", encoding="utf-8")
            review = artifact_path(root, "citation_support_review.json")
            review.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-review/2",
                        "review_mode": "web",
                        "evidence_provenance": {
                            "mode": "web",
                            "provider_name": "shell",
                            "model_review_used": True,
                            "web_search_required": True,
                            "semantic_scholar_required": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            audit = build_reproducibility_audit(root)

        self.assertTrue(audit["citation_support_review_live"])
        self.assertFalse(audit["semantic_scholar_required"])
        self.assertEqual(audit["citation_support_review_provenance"]["mode"], "web")
        self.assertEqual(audit["citation_registry_live_verified_count"], 0)

    def test_provenance_trust_marks_mixed_cited_provenance_as_mixed(self) -> None:
        from paperorchestra.quality_loop import _provenance_trust

        trust = _provenance_trust(
            {
                "verdict": "BLOCK",
                "verification_invoked": True,
                "prompt_trace_file_count": 1,
                "lane_manifest_summary": {"manifest_count": 1},
                "citation_live_provenance": {
                    "registry_count": 1,
                    "seed_only_count": 1,
                    "cited_entry_count": 1,
                    "cited_curated_seed_count": 0,
                    "cited_mixed_count": 1,
                    "status": "mixed",
                },
            }
        )

        self.assertEqual(trust["level"], "mixed")
        self.assertIn("citation_cited_mixed_count=1", trust["mixed_evidence"])

    def test_provenance_trust_ignores_unused_mock_registry_entries(self) -> None:
        from paperorchestra.quality_loop import _provenance_trust

        trust = _provenance_trust(
            {
                "verdict": "OK",
                "verification_invoked": True,
                "prompt_trace_file_count": 1,
                "lane_manifest_summary": {"manifest_count": 1},
                "mock_registry_entry_count": 1,
                "citation_live_provenance": {
                    "registry_count": 2,
                    "mock_entry_count": 1,
                    "cited_entry_count": 1,
                    "cited_mock_count": 0,
                    "cited_curated_seed_count": 0,
                    "cited_mixed_count": 0,
                    "status": "live",
                },
            }
        )

        self.assertEqual(trust["level"], "live")
        self.assertEqual(trust["mock_evidence"], [])

    def test_provenance_trust_marks_cited_mock_entries_as_mock(self) -> None:
        from paperorchestra.quality_loop import _provenance_trust

        trust = _provenance_trust(
            {
                "verdict": "BLOCK",
                "verification_invoked": True,
                "prompt_trace_file_count": 1,
                "lane_manifest_summary": {"manifest_count": 1},
                "mock_registry_entry_count": 1,
                "citation_live_provenance": {
                    "registry_count": 1,
                    "mock_entry_count": 1,
                    "cited_entry_count": 1,
                    "cited_mock_count": 1,
                    "cited_curated_seed_count": 0,
                    "cited_mixed_count": 0,
                    "status": "mock",
                },
            }
        )

        self.assertEqual(trust["level"], "mock")
        self.assertIn("citation_cited_mock_count=1", trust["mock_evidence"])

    def _manual_check_quality_eval(self, review_path: Path, failing_codes: list[str] | None = None) -> dict:
        return {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_support_critic": {
                            "status": "fail",
                            "path": str(review_path),
                            "failing_codes": failing_codes or ["citation_support_manual_check"],
                        }
                    }
                }
            }
        }

    def _write_manual_check_review(self, path: Path, items: list[dict]) -> None:
        summary: dict[str, int] = {}
        for item in items:
            status = str(item.get("support_status") or "needs_manual_check")
            summary[status] = summary.get(status, 0) + 1
        path.write_text(
            json.dumps(
                {
                    "schema_version": "citation-support-review/2",
                    "claims_checked": len(items),
                    "summary": summary,
                    "evidence_provenance": {"claim_support_not_metadata_lookup": True},
                    "items": items,
                }
            ),
            encoding="utf-8",
        )

    def _write_v3_citation_support_review(self, path: Path, cases: list[dict]) -> None:
        summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
        for case in cases:
            verdict = str(case.get("verdict") or "human_needed")
            summary[verdict if verdict in summary else "human_needed"] += 1
        path.write_text(
            json.dumps(
                {
                    "schema": "citation-support-review/3",
                    "mode": "source",
                    "summary": summary,
                    "cases": cases,
                }
            ),
            encoding="utf-8",
        )

    def _citation_action_codes(self, actions: list[dict]) -> set[str]:
        return {str(action.get("code")) for action in actions}

    def _public_action_text(self, actions: list[dict]) -> str:
        public_fields = ["action_id", "code", "target", "automation", "reason", "ralph_instruction", "why_not_automatic"]
        parts: list[str] = []
        for action in actions:
            for field in public_fields:
                parts.append(str(action.get(field, "")))
            parts.extend(str(command) for command in action.get("suggested_commands") or [])
        return "\n".join(parts)

    def _assert_no_private_citation_case_text_in_actions(self, actions: list[dict], *extra_markers: str) -> None:
        public_text = self._public_action_text(actions)
        for marker in [
            "PRIVATE_PARAGRAPH",
            "PRIVATE_ANCHOR",
            "PRIVATE_TARGET",
            "PRIVATE_SOURCE_TITLE",
            "PRIVATE_NOTE",
            "PRIVATE_ASK",
            "PRIVATE_RESOLUTION",
            "private-source",
            *extra_markers,
        ]:
            self.assertNotIn(marker, public_text)

    def _machine_solvable_manual_item(self) -> dict:
        return {
            "id": "manual-1",
            "sentence": "Private raw sentence should not leak.",
            "citation_keys": ["RefA"],
            "citation_entries": [{"key": "RefA", "title": "Reference A", "url": "https://example.invalid/ref-a"}],
            "support_status": "needs_manual_check",
            "suggested_fix": "Scope the claim to the cited reference.",
            "evidence": [
                {
                    "citation_key": "RefA",
                    "source_title": "Reference A",
                    "url": "https://example.invalid/ref-a",
                    "evidence_quote_or_summary": "Reference A supports the narrowed claim.",
                    "supports_claim": True,
                }
            ],
        }


    def test_v3_weak_case_without_legacy_items_does_not_route_to_false_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_v3_citation_support_review(
                review_path,
                [
                    {
                        "id": "C1",
                        "key": "RefA",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_PARAGRAPH Claim text \\cite{RefA}.",
                        "anchor": "PRIVATE_ANCHOR Claim text \\cite{RefA}.",
                        "target": "PRIVATE_TARGET Claim text",
                        "source": {
                            "type": "paper",
                            "title": "PRIVATE_SOURCE_TITLE",
                            "url": "https://example.invalid/private-source",
                        },
                        "evidence": {"status": "metadata"},
                        "verdict": "weak",
                        "note": "PRIVATE_NOTE Metadata only.",
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path, ["citation_support_weak"]))

        codes = self._citation_action_codes(actions)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_evidence_research_needed", codes)
        self._assert_no_private_citation_case_text_in_actions(actions)

    def test_v3_human_needed_blocked_source_routes_to_author_judgment_without_payload_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_v3_citation_support_review(
                review_path,
                [
                    {
                        "id": "C1",
                        "key": "RefA",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_PARAGRAPH blocked source \\cite{RefA}.",
                        "anchor": "PRIVATE_ANCHOR blocked source \\cite{RefA}.",
                        "target": "PRIVATE_TARGET blocked source",
                        "source": {
                            "type": "paper",
                            "title": "PRIVATE_SOURCE_TITLE",
                            "url": "https://example.invalid/private-source",
                        },
                        "evidence": {"status": "blocked", "why": "login_required"},
                        "verdict": "human_needed",
                        "note": "PRIVATE_NOTE source blocked.",
                        "ask": "PRIVATE_ASK provide a source.",
                        "resolution": {"note": "PRIVATE_RESOLUTION not yet provided."},
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = self._citation_action_codes(actions)
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        action = [action for action in actions if action.get("code") == "citation_support_manual_check_requires_author_judgment"][0]
        self.assertIn("1 citation-support manual-check item", action["reason"])
        self.assertNotIn("payload is unavailable", action["reason"])
        self._assert_no_private_citation_case_text_in_actions(actions)

    def test_v3_weak_case_with_author_marker_routes_to_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_v3_citation_support_review(
                review_path,
                [
                    {
                        "id": "C1",
                        "key": "RefA",
                        "paragraph": "PRIVATE_PARAGRAPH author-owned weak claim \\cite{RefA}.",
                        "anchor": "PRIVATE_ANCHOR author-owned weak claim \\cite{RefA}.",
                        "target": "PRIVATE_TARGET author-owned weak claim",
                        "source": {"title": "PRIVATE_SOURCE_TITLE", "url": "https://example.invalid/private-source"},
                        "evidence": {"status": "metadata"},
                        "verdict": "weak",
                        "requires_author_judgment": True,
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path, ["citation_support_weak"]))

        codes = self._citation_action_codes(actions)
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        self._assert_no_private_citation_case_text_in_actions(actions)

    def test_v3_human_needed_with_concrete_unbound_surface_routes_to_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_v3_citation_support_review(
                review_path,
                [
                    {
                        "id": "C2",
                        "key": "RefB",
                        "paragraph": "PRIVATE_PARAGRAPH_B should not leak \\cite{RefB}.",
                        "anchor": "PRIVATE_ANCHOR_B should not leak \\cite{RefB}.",
                        "target": "PRIVATE_TARGET_B should not leak",
                        "source": {
                            "type": "paper",
                            "title": "PRIVATE_SOURCE_TITLE_B",
                            "url": "https://example.invalid/private-source-b",
                        },
                        "evidence": {"status": "metadata"},
                        "verdict": "human_needed",
                        "suggested_fix": "Refresh evidence before rewriting.",
                        "note": "PRIVATE_NOTE_B source surface needs research.",
                        "ask": "PRIVATE_ASK_B inspect the source.",
                        "resolution": {"note": "PRIVATE_RESOLUTION_B not yet provided."},
                        "evidence_surfaces": [
                            {
                                "url": "https://example.invalid/private-source-b",
                                "evidence_quote_or_summary": (
                                    "Concrete unverified surface exists; it must be researched before repair."
                                ),
                            }
                        ],
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = self._citation_action_codes(actions)
        self.assertIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)
        self._assert_no_private_citation_case_text_in_actions(actions, "PRIVATE_PARAGRAPH_B", "PRIVATE_ANCHOR_B", "PRIVATE_TARGET_B", "PRIVATE_SOURCE_TITLE_B", "PRIVATE_NOTE_B", "PRIVATE_ASK_B", "PRIVATE_RESOLUTION_B", "private-source-b")

    def test_v3_verified_support_false_string_does_not_route_to_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_v3_citation_support_review(
                review_path,
                [
                    {
                        "id": "C3",
                        "key": "RefC",
                        "paragraph": "PRIVATE_PARAGRAPH_C should not leak \\cite{RefC}.",
                        "anchor": "PRIVATE_ANCHOR_C should not leak \\cite{RefC}.",
                        "target": "PRIVATE_TARGET_C should not leak",
                        "source": {
                            "type": "paper",
                            "title": "PRIVATE_SOURCE_TITLE_C",
                            "url": "https://example.invalid/private-source-c",
                        },
                        "evidence": {"status": "metadata"},
                        "verdict": "human_needed",
                        "suggested_fix": "Scope claim before rewriting.",
                        "support_evidence": [
                            {
                                "citation_key": "RefC",
                                "source_title": "PRIVATE_SOURCE_TITLE_C",
                                "url": "https://example.invalid/private-source-c",
                                "evidence_quote_or_summary": "This source explicitly does not support the claim.",
                                "supports_claim": "false",
                            }
                        ],
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = self._citation_action_codes(actions)
        self.assertNotIn("citation_support_critic_failed", codes)
        self.assertIn("citation_support_evidence_research_needed", codes)
        self._assert_no_private_citation_case_text_in_actions(actions, "PRIVATE_PARAGRAPH_C", "PRIVATE_ANCHOR_C", "PRIVATE_TARGET_C", "PRIVATE_SOURCE_TITLE_C", "private-source-c")


    def test_v3_case_context_mismatch_routes_to_citation_review_refresh_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            review_path.write_text(
                json.dumps({"schema": "citation-support-review/3", "summary": {}, "cases": []}),
                encoding="utf-8",
            )

            actions = _quality_eval_actions(
                self._manual_check_quality_eval(review_path, ["citation_support_case_context_mismatch"])
            )

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_case_context_mismatch", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        refresh_action = [action for action in actions if action.get("code") == "citation_support_case_context_mismatch"][0]
        self.assertEqual(refresh_action["automation"], "automatic")
        self.assertIn("paperorchestra review-citations --evidence-mode web", refresh_action["suggested_commands"])

    def test_v3_case_coverage_mismatch_routes_to_citation_review_refresh_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            review_path.write_text(
                json.dumps({"schema": "citation-support-review/3", "summary": {}, "cases": []}),
                encoding="utf-8",
            )

            actions = _quality_eval_actions(
                self._manual_check_quality_eval(review_path, ["citation_support_case_coverage_mismatch"])
            )

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_case_coverage_mismatch", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        refresh_action = [action for action in actions if action.get("code") == "citation_support_case_coverage_mismatch"][0]
        self.assertEqual(refresh_action["automation"], "automatic")
        self.assertIn("paperorchestra review-citations --evidence-mode web", refresh_action["suggested_commands"])

    def test_manual_check_with_fix_and_support_evidence_routes_to_semi_auto_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(review_path, [self._machine_solvable_manual_item()])

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)

    def test_manual_check_with_unbound_evidence_routes_to_research_not_repair_or_human(self) -> None:
        item = self._machine_solvable_manual_item()
        item["evidence"][0]["source_title"] = "A different but concrete source surface"
        item["evidence"][0]["url"] = "https://example.invalid/different-source"
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(review_path, [item])

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)
        research_action = [action for action in actions if action.get("code") == "citation_support_evidence_research_needed"][0]
        self.assertEqual(research_action["automation"], "automatic")
        self.assertIn("paperorchestra review-citations --evidence-mode web", research_action["suggested_commands"])
        public_text = "\n".join(str(research_action.get(field, "")) for field in ["reason", "ralph_instruction"])
        self.assertNotIn("Private raw sentence", public_text)
        self.assertNotIn("different but concrete", public_text)

    def test_weak_support_with_unbound_evidence_routes_to_research_not_repair_or_human(self) -> None:
        item = self._machine_solvable_manual_item()
        item["support_status"] = "weakly_supported"
        item["evidence"][0]["source_title"] = "A different but concrete source surface"
        item["evidence"][0]["url"] = "https://example.invalid/different-source"
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(review_path, [item])

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path, ["citation_support_weak"]))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)

    def test_weak_support_with_author_marker_routes_to_human_not_research_or_repair(self) -> None:
        item = self._machine_solvable_manual_item()
        item["support_status"] = "weakly_supported"
        item["requires_author_judgment"] = True
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(review_path, [item])

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path, ["citation_support_weak"]))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_critic_failed", codes)

    def test_mixed_manual_unbound_and_weak_plain_gap_does_not_false_human_needed(self) -> None:
        manual_item = self._machine_solvable_manual_item()
        manual_item["evidence"][0]["source_title"] = "A different but concrete source surface"
        manual_item["evidence"][0]["url"] = "https://example.invalid/different-source"
        weak_item = {
            "id": "weak-1",
            "sentence": "Weak item text should not leak.",
            "citation_keys": ["RefB"],
            "support_status": "weakly_supported",
            "suggested_fix": "Refresh evidence before rewriting.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(review_path, [manual_item, weak_item])

            actions = _quality_eval_actions(
                self._manual_check_quality_eval(review_path, ["citation_support_manual_check", "citation_support_weak"])
            )

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_evidence_research_needed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_critic_failed", codes)

    def test_manual_check_requiring_author_judgment_routes_to_human_needed_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(
                review_path,
                [
                    {
                        "id": "manual-1",
                        "sentence": "Author-domain interpretation is required.",
                        "citation_keys": ["RefA"],
                        "support_status": "needs_manual_check",
                        "requires_author_judgment": True,
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        manual_actions = [action for action in actions if action.get("code") == "citation_support_manual_check_requires_author_judgment"]
        repair_actions = [action for action in actions if action.get("code") == "citation_support_critic_failed"]
        self.assertEqual(len(manual_actions), 1)
        self.assertEqual(manual_actions[0]["automation"], "human_needed")
        self.assertEqual(repair_actions, [])

    def test_mixed_manual_check_emits_repair_and_author_judgment_actions_without_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            author_owned = {
                "id": "manual-2",
                "sentence": "Do not leak this raw author-owned sentence.",
                "citation_keys": ["RefB"],
                "support_status": "needs_manual_check",
                "requires_author_judgment": True,
            }
            self._write_manual_check_review(review_path, [self._machine_solvable_manual_item(), author_owned])

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_critic_failed", codes)
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        joined_public_text = "\n".join(str(action.get("reason", "")) + "\n" + str(action.get("ralph_instruction", "")) for action in actions)
        self.assertNotIn("Private raw sentence", joined_public_text)
        self.assertNotIn("Do not leak this raw author-owned sentence", joined_public_text)

    def test_manual_check_with_only_citation_entries_is_author_judgment_not_machine_solvable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(
                review_path,
                [
                    {
                        "id": "manual-1",
                        "citation_keys": ["RefA"],
                        "citation_entries": [{"key": "RefA", "title": "Reference A", "url": "https://example.invalid/ref-a"}],
                        "support_status": "needs_manual_check",
                        "suggested_fix": "Scope the claim.",
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_evidence_research_needed", codes)

    def test_manual_check_with_missing_payload_fails_closed_to_author_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-citation-support.json"

            actions = _quality_eval_actions(self._manual_check_quality_eval(missing))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_manual_check_requires_author_judgment", codes)
        self.assertNotIn("citation_support_critic_failed", codes)

    def test_metadata_only_citation_support_remains_repairable_not_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "citation_support_review.json"
            self._write_manual_check_review(
                review_path,
                [
                    {
                        "id": "metadata-1",
                        "citation_keys": ["RefA"],
                        "citation_entries": [{"key": "RefA", "title": "Reference A"}],
                        "support_status": "metadata_only",
                    }
                ],
            )

            actions = _quality_eval_actions(self._manual_check_quality_eval(review_path, ["citation_support_metadata_only"]))

        codes = {action.get("code") for action in actions}
        self.assertIn("citation_support_critic_failed", codes)
        self.assertNotIn("citation_support_manual_check_requires_author_judgment", codes)

    def test_qa_loop_step_is_the_budget_consuming_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                result = run_qa_loop_step(root, MockProvider(), max_iterations=5, citation_evidence_mode="heuristic")

            self.assertTrue(result.payload["actions_attempted"])
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            budgeted = [entry for entry in history if entry.get("consumes_budget")]
            self.assertEqual(len(budgeted), 1)
            self.assertEqual(budgeted[0]["event_type"], "qa_loop_step")
            self.assertEqual(budgeted[0]["execution_path"], str(result.path))
            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["attempts_used"], 1)
            self.assertEqual(quality_eval["cross_iteration"]["budget"]["remaining"], 4)


    def test_qa_loop_step_runs_v3_mismatch_citation_review_handlers(self) -> None:
        for code in ["citation_support_case_context_mismatch", "citation_support_case_coverage_mismatch"]:
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    state = self._init_session_with_minimal_inputs(root)
                    paper = artifact_path(root, "paper.full.tex")
                    paper.write_text(
                        "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                        "QUIC uses TLS~\\cite{RFC9001}.\n"
                        "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                        encoding="utf-8",
                    )
                    state.artifacts.paper_full_tex = str(paper)
                    save_session(root, state)
                    write_planning_artifacts(root)
                    record_current_validation_report(root, name="validation.current.json")
                    write_figure_placement_review(root)

                    before_eval = {
                        "session_id": "po-test",
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": [code],
                            }
                        },
                    }
                    after_eval = {
                        "session_id": "po-test",
                        "mode": "claim_safe",
                        "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
                    }
                    before_plan = {
                        "verdict": "continue",
                        "repair_actions": [{"code": code, "automation": "automatic"}],
                    }
                    after_plan = {"verdict": "human_needed", "repair_actions": []}
                    with patch(
                        "paperorchestra.ralph_bridge.write_quality_eval",
                        side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)],
                    ):
                        with patch(
                            "paperorchestra.ralph_bridge.write_quality_loop_plan",
                            side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)],
                        ):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation_support_review.json") as review:
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

                    review.assert_called()
                    attempted = result.payload.get("actions_attempted", [])
                    self.assertTrue(attempted)
                    self.assertEqual(attempted[0]["code"], code)
                    self.assertEqual(attempted[0]["handler"], "review_citations")

    def test_qa_loop_step_runs_missing_citation_review_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)],
                ):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertTrue(result.path.exists())
            self.assertIn(result.exit_code, {10, 20, 30})
            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review_citations", handlers)
            citation_review_path = Path(load_session(root).artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
            self.assertTrue(citation_review_path.exists())

    def test_qa_loop_step_runs_source_obligations_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["source_obligations_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "source_obligations_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("build_source_obligations", handlers)
            self.assertTrue(Path(load_session(root).artifacts.source_obligations_json).exists())

    def test_qa_loop_step_runs_tier0_precondition_refresh_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {
                        "status": "fail",
                        "failing_codes": [
                            "narrative_plan_stale",
                            "validation_report_missing",
                            "figure_placement_review_missing",
                        ],
                    }
                },
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_0_preconditions": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [
                    {"code": "narrative_plan_stale", "automation": "automatic"},
                    {"code": "validation_report_missing", "automation": "automatic"},
                    {"code": "figure_placement_review_missing", "automation": "automatic"},
                ],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            attempted = result.payload.get("actions_attempted", [])
            handlers = [item.get("handler") for item in attempted]
            self.assertIn("plan_narrative", handlers)
            self.assertIn("validate_current", handlers)
            self.assertIn("review_figure_placement", handlers)
            planning_actions = [item for item in attempted if item.get("handler") == "plan_narrative"]
            validation_actions = [item for item in attempted if item.get("handler") == "validate_current"]
            figure_actions = [item for item in attempted if item.get("handler") == "review_figure_placement"]
            self.assertTrue(Path(planning_actions[0]["paths"]["narrative_plan"]).exists())
            self.assertTrue(Path(validation_actions[0]["path"]).exists())
            self.assertTrue(Path(figure_actions[0]["path"]).exists())
            state = load_session(root)
            self.assertIsNotNone(state.artifacts.narrative_plan_json)
            self.assertIsNotNone(state.artifacts.latest_validation_json)
            self.assertIsNotNone(state.artifacts.latest_figure_placement_review_json)

    def test_qa_loop_step_runs_new_review_validation_refresh_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "warn", "failing_codes": ["review_provenance_missing"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_3_scholarly_quality": {"status": "pass", "failing_codes": []}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "review_provenance_missing", "automation": "automatic"}],
            }
            after_plan = {"verdict": "human_needed", "repair_actions": []}
            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=[(root / "before-q.json", before_eval), (root / "after-q.json", after_eval)]):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=[(root / "before-p.json", before_plan), (root / "after-p.json", after_plan)]):
                    with patch("paperorchestra.ralph_bridge.review_current_paper", return_value=root / "review.json"):
                        result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            handlers = [item.get("handler") for item in result.payload.get("actions_attempted", [])]
            self.assertIn("review", handlers)

    def test_qa_loop_step_stops_on_unsupported_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["compile_not_clean"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [
                    {
                        "code": "unknown_citation_keys",
                        "automation": "automatic",
                        "reason": "No bridge handler exists for this synthetic action.",
                    }
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertEqual(result.payload["reason"], "no_supported_executable_handlers")
            self.assertEqual(result.payload["actions_skipped"][0]["code"], "unknown_citation_keys")

    def test_qa_loop_step_noops_on_terminal_human_needed_even_with_executable_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_1_structural": {"status": "fail", "failing_codes": ["missing_prompt_trace"]}},
            }
            plan = {
                "verdict": "human_needed",
                "repair_actions": [
                    {"code": "missing_prompt_trace", "automation": "human_needed"},
                    {"code": "citation_support_review_missing", "automation": "automatic"},
                ],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review") as review_citations:
                            result = run_qa_loop_step(root, MockProvider())

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertTrue(result.payload["terminal_noop"])
            self.assertEqual(result.payload["actions_attempted"], [])
            self.assertEqual(result.payload["actions_skipped"], [])
            review_citations.assert_not_called()

    def test_qa_loop_step_uses_explicit_quality_eval_and_plan_without_regenerating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}Current.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_hash = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            quality_eval_path = artifact_path(root, "quality-eval.custom.json")
            quality_eval_path.write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "manuscript_hash": manuscript_hash,
                        "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
                    }
                ),
                encoding="utf-8",
            )
            plan_path = artifact_path(root, "qa-loop.plan.custom.json")
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/1",
                        "session_id": state.session_id,
                        "verdict": "human_needed",
                        "quality_eval_summary": {"manuscript_hash": manuscript_hash},
                        "source_artifacts": {"quality_eval": str(quality_eval_path)},
                        "reads": {
                            "quality_eval": f"{quality_eval_path}@sha256:{hashlib.sha256(quality_eval_path.read_bytes()).hexdigest()}"
                        },
                        "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
                    }
                ),
                encoding="utf-8",
            )

            with patch("paperorchestra.ralph_bridge.write_quality_eval", side_effect=AssertionError("regenerated quality eval")):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=AssertionError("regenerated plan")):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        result = run_qa_loop_step(
                            root,
                            MockProvider(),
                            quality_eval_input_path=quality_eval_path,
                            qa_loop_plan_input_path=plan_path,
                        )

        self.assertEqual(result.payload["verdict"], "human_needed")
        self.assertTrue(result.payload["terminal_noop"])
        self.assertEqual(result.payload["input_quality_eval"], str(quality_eval_path.resolve()))
        self.assertEqual(result.payload["input_plan"], str(plan_path.resolve()))

    def test_qa_loop_step_rejects_stale_explicit_citation_support_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}Current.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            review = root / "round-2" / "citation_support_review.json"
            review.parent.mkdir()
            review.write_text(
                json.dumps({"schema_version": "citation-support-review/2", "manuscript_sha256": "not-current"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "citation-support review input is stale for the current manuscript"):
                run_qa_loop_step(root, MockProvider(), citation_support_review_path=review)

    def test_operator_review_packet_requires_terminal_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="continue")
            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertEqual(packet["review_scope"], "tex_only")
            self.assertIn("qa_loop_plan", {artifact["role"] for artifact in packet["artifacts"]})

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, require_pdf=True)

    def test_operator_review_packet_rejects_stale_human_needed_execution_without_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                            "reason": "semi_auto candidate requires supervised approval",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertTrue(packet_path.exists())
            self.assertIn("qa_loop_execution", {artifact["role"] for artifact in packet["artifacts"]})
            issue = {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_approval",
                "target_section": "Whole manuscript",
                "severity": "major",
                "rationale": "The latest QA-loop execution requires supervised approval.",
                "suggested_action": "Review and apply the candidate only if it preserves claim safety.",
                "authority_class": "author_feedback",
                "owner_category": "author",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
            )
            issue["source"] = "codex_operator"
            issue["not_independent_human_review"] = True
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(
                root,
                packet_path=packet_path,
                feedback_path=feedback_path,
            )
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_operator_review_packet_accepts_hash_bound_candidate_approval_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "paper.citation-repair.candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft with a narrowed claim.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-06T00:00:00Z",
                    "reason": "Semi-automatic citation repair made progress and needs supervised approval.",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_weak"],
                    "resolved_codes": ["citation_support_manual_check"],
                    "new_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            stale_operator_execution = artifact_path(root, "operator_feedback.execution.json")
            stale_operator_execution.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "manuscript_sha256_before": "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest(),
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                suggested_action="Promote the candidate only after preserving the remaining weak citation warning.",
            )
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the hash-bound candidate because it resolves a manual-check citation issue.",
                                "suggested_action": "Promote the candidate only after preserving the remaining weak citation warning.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "approve_existing_candidate")

            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "failed",
                        "quality_eval_summary": {"manuscript_hash": base_sha},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"):
                import_operator_feedback(
                    root,
                    packet_path=packet_path,
                    feedback_path=feedback_path,
                    output_path=root / "stale-candidate-context.json",
                )

    def test_operator_review_packet_accepts_hash_bound_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "actions_attempted": [
                            {"code": "citation_support_critic_failed", "handler": "repair_citation_claims"}
                        ],
                        "candidate_handoff": {
                            "status": "human_needed_candidate_rejected_by_citation_support",
                            "reason": "candidate still has non-reviewable citation-support failures",
                        },
                        "candidate_rollback": {
                            "reason": "citation_support_approval_failed",
                            "failing_codes": ["citation_support_weak"],
                        },
                        "progress": {
                            "before_manuscript_hash": base_sha,
                            "after_manuscript_hash": base_sha,
                            "same_manuscript_as_previous": True,
                            "forward_progress": False,
                            "before_failing_codes": ["citation_support_weak"],
                            "after_failing_codes": ["citation_support_weak"],
                        },
                        "restored_current_state": {
                            "qa_loop_plan_verdict": "continue",
                            "progress": {
                                "before_manuscript_hash": base_sha,
                                "after_manuscript_hash": base_sha,
                                "forward_progress": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertIn("qa_loop_execution", roles)
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            self.assertEqual(json.loads(Path(qa_plan_record["path"]).read_text(encoding="utf-8"))["verdict"], "continue")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_execution",
                source_item_key="candidate_handoff",
                target_section="Whole manuscript",
                rationale="The latest QA-loop execution exhausted the bounded candidate repair lane.",
                suggested_action="Generate a new operator candidate grounded in the packet artifacts.",
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
                                "source_artifact_role": "qa_loop_execution",
                                "source_item_key": "candidate_handoff",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The latest QA-loop execution exhausted the bounded candidate repair lane.",
                                "suggested_action": "Generate a new operator candidate grounded in the packet artifacts.",
                                "authority_class": "author_feedback",
                                "owner_category": "author",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_rejects_stale_rejected_candidate_stop_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            stale_sha = "sha256:" + hashlib.sha256(b"stale manuscript").hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "candidate_handoff": {"status": "human_needed_candidate_rejected_by_citation_support"},
                        "progress": {
                            "before_manuscript_hash": stale_sha,
                            "after_manuscript_hash": stale_sha,
                            "forward_progress": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_operator_review_packet_rejects_operator_execution_only_reopen_with_continue_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="continue")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ContractError):
                build_operator_review_packet(root, review_scope="tex_only")

    def test_current_human_needed_plan_ignores_stale_supplemental_executions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            old_paper = artifact_path(root, "old-paper.full.tex")
            old_paper.write_text("\\documentclass{article}\n\\begin{document}\nOld.\n\\end{document}\n", encoding="utf-8")
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nCurrent.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(old_paper.read_bytes()).hexdigest()
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            self.assertNotEqual(old_sha, current_sha)
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                    }
                ),
                encoding="utf-8",
            )
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": old_sha,
                        "promotion_status": "rolled_back",
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("qa_loop_execution", roles)
            self.assertNotIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The current plan is human-needed even though old execution artifacts exist.",
                suggested_action="Continue supervised feedback from the current plan only.",
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
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The current plan is human-needed even though old execution artifacts exist.",
                                "suggested_action": "Continue supervised feedback from the current plan only.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_review_packet_omits_stale_review_artifacts_for_current_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            old_sha = "sha256:" + hashlib.sha256(b"old manuscript").hexdigest()
            artifact_path(root, "section_review.json").write_text(
                json.dumps({"schema_version": "section-review/1", "manuscript_sha256": old_sha, "sections": []}),
                encoding="utf-8",
            )
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps({"schema_version": "citation-support-review/1", "manuscript_sha256": old_sha, "items": []}),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": old_sha, "tiers": {}}),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            self.assertTrue(packet_path.exists())
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_plan", roles)
            self.assertNotIn("section_review", roles)
            self.assertNotIn("citation_support_review", roles)
            self.assertNotIn("quality_eval", roles)

    def test_operator_review_packet_uses_current_fallback_when_state_pointer_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Intro}\n"
                "Draft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            current_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            stale_section = artifact_path(root, "stale-section-review.json")
            stale_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": "sha256:" + hashlib.sha256(b"old manuscript").hexdigest(),
                        "sections": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.latest_section_review_json = str(stale_section)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            current_section = artifact_path(root, "section_review.json")
            current_section.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_sha256": current_sha,
                        "sections": [{"title": "Intro", "score": 55}],
                    }
                ),
                encoding="utf-8",
            )

            _packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            by_role = {artifact["role"]: artifact for artifact in packet["artifacts"]}
            self.assertIn("section_review", by_role)
            self.assertEqual(Path(by_role["section_review"]["original_path"]).resolve(), current_section.resolve())

    def test_operator_review_payload_includes_concrete_claim_safety_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-review/1",
                        "items": [
                            {
                                "id": "cite-001",
                                "support_status": "supported",
                                "sentence": "Supported sentence.",
                                "citation_keys": ["GoodKey"],
                            },
                            {
                                "id": "cite-002",
                                "support_status": "unsupported",
                                "claim_type": "numeric",
                                "risk": "high",
                                "sentence": "Exact bound unsupported by the provided citation.",
                                "citation_keys": ["WeakKey"],
                                "suggested_fix": "Remove the exact bound or cite the exact lemma.",
                                "model_reasoning": "The citation does not establish the numeric denominator.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "checks": {
                                    "high_risk_claim_sweep": {
                                        "status": "fail",
                                        "items": [
                                            {
                                                "line": 12,
                                                "sentence": "High-risk uncited security claim.",
                                                "reason": "high-risk claim lacks citation",
                                            }
                                        ],
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue = {
                "source_artifact_role": "citation_support_review",
                "source_item_key": "non_supported_items",
                "target_section": "Whole manuscript",
                "severity": "critical",
                "rationale": "Citation support failed.",
                "suggested_action": "Fix the concrete unsupported claims.",
                "authority_class": "author_feedback",
            }
            issue["id"] = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role=issue["source_artifact_role"],
                source_item_key=issue["source_item_key"],
                target_section=issue["target_section"],
                rationale=issue["rationale"],
                suggested_action=issue["suggested_action"],
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
                        "issues": [issue],
                    }
                ),
                encoding="utf-8",
            )
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            review_payload = _operator_review_payload(imported)

            context = review_payload["issue_context"]
            self.assertEqual(context["problematic_citation_items"][0]["id"], "cite-002")
            self.assertIn("Exact bound unsupported", context["problematic_citation_items"][0]["sentence"])
            self.assertEqual(context["high_risk_uncited_claims"][0]["line"], 12)
            self.assertIn("High-risk uncited security claim", context["high_risk_uncited_claims"][0]["sentence"])
            self.assertIn("primary repair targets", context["writer_instruction"])
            self.assertIn("refinement_constraints", context)
            self.assertIn("citation_support_weak", context["refinement_constraints"]["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_manual_check", context["refinement_constraints"]["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_metadata_only", context["refinement_constraints"]["forbidden_new_tier2_codes"])
            self.assertIn("citation_support_evidence_missing", context["refinement_constraints"]["forbidden_new_tier2_codes"])
            self.assertIn("high_risk_uncited_claim", context["refinement_constraints"]["forbidden_new_tier2_codes"])

    def test_operator_issue_context_includes_duplicate_support_from_packet(self) -> None:
        from paperorchestra.operator_feedback import _operator_issue_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "One claim~\\cite{Repeat}. Another claim~\\cite{Repeat}. "
                "Third claim~\\cite{Repeat}. Fourth claim~\\cite{Repeat}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema_version": "citation-support-review/1",
                        "items": [
                            {
                                "id": f"cite-{idx}",
                                "support_status": "supported",
                                "claim_type": "background",
                                "sentence": f"Claim {idx} uses the repeated source.",
                                "citation_keys": ["Repeat"],
                            }
                            for idx in range(1, 5)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "citation_integrity.audit.json").write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-audit/1",
                        "status": "fail",
                        "failing_codes": ["citation_duplicate_support"],
                        "checks": {
                            "duplicate_support": {
                                "status": "fail",
                                "duplicate_keys": ["Repeat"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, _packet = build_operator_review_packet(root, review_scope="tex_only")

            context = _operator_issue_context({"packet_path": str(packet_path)})

            duplicate = context["citation_duplicate_support_issues"]
            self.assertEqual(duplicate[0]["issue_type"], "citation_duplicate_support")
            self.assertEqual(duplicate[0]["citation_key"], "Repeat")
            self.assertEqual(duplicate[0]["occurrence_count"], 4)
            self.assertEqual(duplicate[0]["affected_items"][0]["id"], "cite-1")
            self.assertIn("without adding bibliography keys", duplicate[0]["suggested_fix"])

    def test_content_refinement_prompt_names_citation_density_issue_context(self) -> None:
        prompt = Path("paperorchestra/prompt_assets/content_refinement_agent.md").read_text(encoding="utf-8")

        self.assertIn("issue_context.citation_density_issues", prompt)
        self.assertIn("issue_context.citation_duplicate_support_issues", prompt)
        self.assertIn("issue_context.figure_placement_issues", prompt)
        self.assertIn("issue_context.refinement_constraints", prompt)
        self.assertIn("do not add new bibliography keys", prompt.lower())
        self.assertIn("do not introduce new dense citation bundles", prompt.lower())

    def test_operator_feedback_cli_trio_smoke_runs_explicit_supervised_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Intro}\nDraft.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli_main(["plan-narrative", "--provider", "mock"]), 0)
                self._write_terminal_human_needed_plan(root)
                packet_stdout = io.StringIO()
                with contextlib.redirect_stdout(packet_stdout):
                    self.assertEqual(cli_main(["build-operator-review-packet", "--review-scope", "tex_only"]), 0)
                packet_payload = json.loads(packet_stdout.getvalue())
                packet = packet_payload["packet"]
                packet_path = packet_payload["path"]
                issue_id = derive_operator_issue_id(
                    packet["packet_sha256"],
                    source_artifact_role="paper_full_tex",
                    source_item_key="Intro:p1",
                    target_section="Intro",
                    rationale="The opening is too thin to be worth external review.",
                    suggested_action="Add a concrete contribution paragraph without inventing new evidence.",
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
                                    "source_artifact_role": "paper_full_tex",
                                    "source_item_key": "Intro:p1",
                                    "target_section": "Intro",
                                    "severity": "major",
                                    "rationale": "The opening is too thin to be worth external review.",
                                    "suggested_action": "Add a concrete contribution paragraph without inventing new evidence.",
                                    "authority_class": "prose_rewrite",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                import_stdout = io.StringIO()
                with contextlib.redirect_stdout(import_stdout):
                    self.assertEqual(
                        cli_main(["import-operator-feedback", "--packet", packet_path, "--feedback", str(feedback_path)]),
                        0,
                    )
                imported_payload = json.loads(import_stdout.getvalue())
                imported_path = imported_payload["path"]
                self.assertEqual(imported_payload["imported_feedback"]["translated_actions"][0]["source_issue_id"], issue_id)

                apply_stdout = io.StringIO()
                with contextlib.redirect_stdout(apply_stdout):
                    apply_code = cli_main(
                        [
                            "apply-operator-feedback",
                            "--imported-feedback",
                            imported_path,
                            "--provider",
                            "mock",
                            "--quality-mode",
                            "draft",
                            "--citation-evidence-mode",
                            "heuristic",
                        ]
                    )
                self.assertEqual(apply_code, 0)
                execution_payload = json.loads(apply_stdout.getvalue())["execution"]
                self.assertEqual(execution_payload["event_type"], "operator_feedback_cycle")
                self.assertTrue(execution_payload["not_independent_human_review"])
                self.assertIn(execution_payload["verdict"], {"human_needed", "continue", "ready_for_human_finalization", "failed"})
                self.assertTrue(Path(execution_payload["incorporation_report"]).exists())
            finally:
                os.chdir(old_cwd)

    def test_import_operator_feedback_requires_machine_readable_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_operator_feedback_packet_import_is_hash_bound_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            feedback = {
                "schema_version": "operator-feedback/1",
                "source": "codex_operator",
                "not_independent_human_review": True,
                "intent": "generate_new_operator_candidate",
                "packet_sha256": packet["packet_sha256"],
                "manuscript_sha256": packet["manuscript_sha256"],
                "issues": [
                    {
                        "id": issue_id,
                        "source_artifact_role": "paper_full_tex",
                        "source_item_key": "Intro:p1",
                        "target_section": "Intro",
                        "severity": "major",
                        "rationale": "The opening does not state the research contribution.",
                        "suggested_action": "Rewrite the introduction around the concrete contribution and evidence boundary.",
                        "authority_class": "prose_rewrite",
                    }
                ],
            }
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps(feedback), encoding="utf-8")

            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["issues"][0]["id"], issue_id)
            self.assertEqual(imported["translated_actions"][0]["source_issue_id"], issue_id)
            self.assertTrue(imported["not_independent_human_review"])

            repeat_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The opening does not state the research contribution.",
                suggested_action="Rewrite the introduction around the concrete contribution and evidence boundary.",
            )
            self.assertEqual(repeat_id, issue_id)

            paper.write_text(paper.read_text(encoding="utf-8") + "% changed\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale-current.json")

            frozen_paper = Path(next(artifact["path"] for artifact in packet["artifacts"] if artifact["role"] == "paper_full_tex"))
            frozen_paper.write_text(frozen_paper.read_text(encoding="utf-8") + "% tampered\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "stale.json")
            self.assertTrue(imported_path.exists())

    def test_operator_feedback_cycle_is_supervised_and_does_not_consume_automatic_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            review = review_path(root, "review.latest.json")
            review.write_text(
                json.dumps(
                    {
                        "overall_score": 50,
                        "axis_scores": {},
                        "summary": {"weaknesses": ["thin"], "top_improvements": ["improve"]},
                        "questions": [],
                        "penalties": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction is too thin.",
                suggested_action="Add a sharper contribution paragraph.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction is too thin.",
                                "suggested_action": "Add a sharper contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nA sharper contribution paragraph.\n", encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:after", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["event_type"], "operator_feedback_cycle")
            self.assertEqual(execution["supervised_iteration_index"], 1)
            self.assertTrue(execution["not_independent_human_review"])
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"reflected", "partially_reflected"})

            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertFalse(history[-1]["consumes_budget"])
            self.assertEqual(history[-1]["supervised_max_iterations"], 1)

    def test_operator_feedback_second_attempt_receives_rejection_memory_and_repeated_candidate_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft claim.\n\\end{document}\n",
                encoding="utf-8",
            )
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 50, "axis_scores": {}, "summary": {}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            base_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                        "checks": {
                            "citation_support_critic": {
                                "needs_manual_check_count": 3,
                                "weakly_supported_count": 5,
                            }
                        },
                    }
                },
            }
            artifact_path(root, "quality-eval.json").write_text(json.dumps(base_quality_eval), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction needs claim-safe citation repair.",
                suggested_action="Repair citation support without increasing manual-check burden.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction needs claim-safe citation repair.",
                                "suggested_action": "Repair citation support without increasing manual-check burden.",
                                "authority_class": "citation_repair",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            reviews_seen: list[dict[str, Any]] = []

            def fake_refine(cwd, provider, **kwargs):
                review_payload = json.loads(Path(load_session(cwd).artifacts.latest_review_json).read_text(encoding="utf-8"))
                reviews_seen.append(review_payload)
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRepeated candidate repair.\n\\end{document}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            candidate_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check"],
                        "checks": {
                            "citation_support_critic": {
                                "needs_manual_check_count": 4,
                                "weakly_supported_count": 2,
                            }
                        },
                    }
                },
            }
            quality_side_effects = [
                (root / "quality-attempt-1.json", candidate_quality_eval),
                (root / "quality-attempt-2.json", candidate_quality_eval),
                (root / "quality-rollback.json", base_quality_eval),
            ]
            for path, payload in quality_side_effects:
                path.write_text(json.dumps(payload), encoding="utf-8")

            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_figure_placement_review", return_value=(root / "figure.json", {"manuscript_sha256": "sha256:test"})):
                            with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                    with patch("paperorchestra.operator_feedback.write_rendered_reference_audit", return_value=root / "rendered.json"):
                                        with patch("paperorchestra.operator_feedback.write_citation_integrity_audit", return_value=root / "integrity.json"):
                                            with patch("paperorchestra.operator_feedback.write_citation_integrity_critic", return_value=root / "critic.json"):
                                                with patch("paperorchestra.operator_feedback.write_quality_eval", side_effect=quality_side_effects):
                                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                                        _, execution = apply_operator_feedback(
                                                            root,
                                                            MockProvider(),
                                                            imported_feedback_path=imported_path,
                                                            max_supervised_iterations=2,
                                                        )

            self.assertEqual(len(reviews_seen), 2)
            self.assertNotIn("prior_rejected_attempts", reviews_seen[0]["issue_context"])
            prior_memory = reviews_seen[1]["issue_context"]["prior_rejected_attempts"]
            self.assertEqual(prior_memory[0]["gate_reasons"], ["active_tier2_metric_regression"])
            self.assertEqual(prior_memory[0]["metric_regressions"][0]["code"], "citation_support_manual_check")
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(len(execution["attempts"]), 2)
            self.assertIn("repeated_non_promotable_candidate", execution["attempts"][1]["gate_reasons"])
            self.assertNotIn("candidate_approval", execution)

    def test_operator_feedback_first_attempt_receives_packet_carried_prior_rejection_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft claim.\n\\end{document}\n"
            repeated = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRepeated cross-cycle repair.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 50, "axis_scores": {}, "summary": {}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            original_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
            repeated_sha = hashlib.sha256(repeated.encode("utf-8")).hexdigest()
            base_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + original_sha,
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                        "checks": {
                            "citation_support_critic": {
                                "needs_manual_check_count": 3,
                                "weakly_supported_count": 5,
                            }
                        },
                    }
                },
            }
            artifact_path(root, "quality-eval.json").write_text(json.dumps(base_quality_eval), encoding="utf-8")
            artifact_path(root, "operator_feedback.execution.json").write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": original_sha,
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:" + repeated_sha,
                                "gate_passed": False,
                                "gate_reasons": ["active_tier2_metric_regression"],
                                "base_active_failures": ["citation_support_manual_check", "citation_support_weak"],
                                "candidate_active_failures": ["citation_support_manual_check"],
                                "resolved_active_failures": ["citation_support_weak"],
                                "new_tier2_failures": [],
                                "active_tier2_metric_delta": {
                                    "regressions": [{"code": "citation_support_manual_check", "before": 3, "after": 4, "delta": 1}],
                                    "improvements": [{"code": "citation_support_weak", "before": 5, "after": 2, "delta": -3}],
                                    "base_total": 8,
                                    "candidate_total": 6,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            self.assertIn("operator_feedback_execution", {artifact["role"] for artifact in packet["artifacts"]})
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="attempts[0]",
                target_section="Intro",
                rationale="The previous operator cycle found a metric-regressing repair.",
                suggested_action="Generate a different repair that does not regress active citation metrics.",
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
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "attempts[0]",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The previous operator cycle found a metric-regressing repair.",
                                "suggested_action": "Generate a different repair that does not regress active citation metrics.",
                                "authority_class": "citation_repair",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            reviews_seen: list[dict[str, Any]] = []

            def fake_refine(cwd, provider, **kwargs):
                reviews_seen.append(json.loads(Path(load_session(cwd).artifacts.latest_review_json).read_text(encoding="utf-8")))
                Path(load_session(cwd).artifacts.paper_full_tex).write_text(repeated, encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            candidate_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check"],
                        "checks": {"citation_support_critic": {"needs_manual_check_count": 4, "weakly_supported_count": 2}},
                    }
                },
            }
            quality_side_effects = [
                (root / "quality-attempt-1.json", candidate_quality_eval),
                (root / "quality-rollback.json", base_quality_eval),
            ]
            for path, payload in quality_side_effects:
                path.write_text(json.dumps(payload), encoding="utf-8")

            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_figure_placement_review", return_value=(root / "figure.json", {"manuscript_sha256": "sha256:test"})):
                            with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                    with patch("paperorchestra.operator_feedback.write_rendered_reference_audit", return_value=root / "rendered.json"):
                                        with patch("paperorchestra.operator_feedback.write_citation_integrity_audit", return_value=root / "integrity.json"):
                                            with patch("paperorchestra.operator_feedback.write_citation_integrity_critic", return_value=root / "critic.json"):
                                                with patch("paperorchestra.operator_feedback.write_quality_eval", side_effect=quality_side_effects):
                                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                                        _, execution = apply_operator_feedback(
                                                            root,
                                                            MockProvider(),
                                                            imported_feedback_path=imported_path,
                                                            max_supervised_iterations=1,
                                                        )

            memory = reviews_seen[0]["issue_context"]["prior_rejected_attempts"]
            self.assertEqual(memory[0]["candidate_sha256"], "sha256:" + repeated_sha)
            self.assertEqual(memory[0]["gate_reasons"], ["active_tier2_metric_regression"])
            self.assertIn("repeated_non_promotable_candidate", execution["attempts"][0]["gate_reasons"])
            self.assertNotIn("candidate_approval", execution)

    def test_operator_feedback_ignores_stale_packet_carried_prior_rejection_memory(self) -> None:
        from paperorchestra.operator_feedback_packets import _file_sha256, _packet_sha256

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft claim.\n\\end{document}\n"
            repeated = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRepeated stale repair.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 50, "axis_scores": {}, "summary": {}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            original_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
            stale_sha = hashlib.sha256(b"stale manuscript").hexdigest()
            repeated_sha = hashlib.sha256(repeated.encode("utf-8")).hexdigest()
            base_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "manuscript_hash": "sha256:" + original_sha,
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                        "checks": {
                            "citation_support_critic": {
                                "needs_manual_check_count": 3,
                                "weakly_supported_count": 5,
                            }
                        },
                    }
                },
            }
            artifact_path(root, "quality-eval.json").write_text(json.dumps(base_quality_eval), encoding="utf-8")
            artifact_path(root, "operator_feedback.execution.json").write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": original_sha,
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:" + repeated_sha,
                                "gate_passed": False,
                                "gate_reasons": ["active_tier2_metric_regression"],
                                "base_active_failures": ["citation_support_manual_check", "citation_support_weak"],
                                "candidate_active_failures": ["citation_support_manual_check"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            operator_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "operator_feedback_execution")
            Path(operator_record["path"]).write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": "sha256:" + stale_sha,
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:" + repeated_sha,
                                "gate_passed": False,
                                "gate_reasons": ["active_tier2_metric_regression"],
                                "base_active_failures": ["citation_support_manual_check", "citation_support_weak"],
                                "candidate_active_failures": ["citation_support_manual_check"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            operator_record["sha256"] = _file_sha256(operator_record["path"])
            operator_record["size_bytes"] = Path(operator_record["path"]).stat().st_size
            packet["packet_sha256"] = _packet_sha256(packet)
            Path(packet_path).write_text(json.dumps(packet, sort_keys=True, indent=2), encoding="utf-8")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Intro",
                rationale="The current human-needed plan requests a different supervised repair.",
                suggested_action="Generate a repair from current artifacts only.",
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
                                "source_item_key": "verdict",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The current human-needed plan requests a different supervised repair.",
                                "suggested_action": "Generate a repair from current artifacts only.",
                                "authority_class": "citation_repair",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            reviews_seen: list[dict[str, Any]] = []

            def fake_refine(cwd, provider, **kwargs):
                reviews_seen.append(json.loads(Path(load_session(cwd).artifacts.latest_review_json).read_text(encoding="utf-8")))
                Path(load_session(cwd).artifacts.paper_full_tex).write_text(repeated, encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            candidate_quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_manual_check"],
                        "checks": {"citation_support_critic": {"needs_manual_check_count": 4, "weakly_supported_count": 2}},
                    }
                },
            }
            quality_side_effects = [
                (root / "quality-attempt-1.json", candidate_quality_eval),
                (root / "quality-rollback.json", base_quality_eval),
            ]
            for path, payload in quality_side_effects:
                path.write_text(json.dumps(payload), encoding="utf-8")

            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_figure_placement_review", return_value=(root / "figure.json", {"manuscript_sha256": "sha256:test"})):
                            with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                    with patch("paperorchestra.operator_feedback.write_rendered_reference_audit", return_value=root / "rendered.json"):
                                        with patch("paperorchestra.operator_feedback.write_citation_integrity_audit", return_value=root / "integrity.json"):
                                            with patch("paperorchestra.operator_feedback.write_citation_integrity_critic", return_value=root / "critic.json"):
                                                with patch("paperorchestra.operator_feedback.write_quality_eval", side_effect=quality_side_effects):
                                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                                        _, execution = apply_operator_feedback(
                                                            root,
                                                            MockProvider(),
                                                            imported_feedback_path=imported_path,
                                                            max_supervised_iterations=1,
                                                        )

            self.assertNotIn("prior_rejected_attempts", reviews_seen[0].get("issue_context", {}))
            self.assertNotIn("repeated_non_promotable_candidate", execution["attempts"][0]["gate_reasons"])
            self.assertNotIn("candidate_approval", execution)

    def test_repeated_non_promotable_reason_is_not_human_reviewable(self) -> None:
        from paperorchestra.operator_feedback import _candidate_attempt_ready_for_human_review

        with tempfile.NamedTemporaryFile(suffix=".tex") as candidate:
            attempt = {
                "candidate_path": candidate.name,
                "resolved_active_failures": ["citation_support_weak"],
                "new_tier2_failures": [],
                "gate_reasons": ["repeated_non_promotable_candidate"],
            }

            self.assertFalse(_candidate_attempt_ready_for_human_review(attempt))

    def test_operator_feedback_candidate_verification_refreshes_citation_integrity_for_staged_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "Draft background~\\cite{Prior}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            candidate = original.replace("Draft background", "Candidate background")
            paper.write_text(original, encoding="utf-8")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{Prior, title={Prior Work}, author={Alice}, year={2024}}\n", encoding="utf-8")
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{Prior} Prior Work.\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                citation_integrity_critic_path,
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            stale_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(stale_critic["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

            candidate_path = artifact_path(root, "paper.operator-test.candidate.tex")
            candidate_path.write_text(candidate, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(candidate_path)
            save_session(root, state)
            def fake_citation_review(cwd, **kwargs):
                support = artifact_path(cwd, "citation_support_review.json")
                support.write_text(
                    json.dumps(
                        {
                            "evidence_mode": "web",
                            "items": [
                                {
                                    "id": "s1",
                                    "sentence": "Candidate background~\\cite{Prior}.",
                                    "citation_keys": ["Prior"],
                                    "support_status": "supported",
                                    "evidence": [{"url": "https://example.test/prior"}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return support

            from paperorchestra.operator_feedback import _tier_failing_codes, _verification_block, _verification_snapshot

            with patch("paperorchestra.operator_feedback.write_citation_support_review", side_effect=fake_citation_review):
                with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                    verification = _verification_snapshot(
                        root,
                        provider=MockProvider(),
                        require_compile=False,
                        quality_mode="claim_safe",
                        max_iterations=5,
                        require_live_verification=False,
                        accept_mixed_provenance=False,
                        runtime_mode="compatibility",
                        citation_evidence_mode="heuristic",
                        citation_provider_name="mock",
                        citation_provider_command=None,
                        validation_name="validation.operator-feedback.attempt-01.json",
                    )

            tier2_failures = set(_tier_failing_codes(verification["quality_eval"], "tier_2_claim_safety"))
            self.assertNotIn("citation_critic_stale", tier2_failures)
            self.assertNotIn("citation_integrity_stale", tier2_failures)
            self.assertNotIn("rendered_reference_audit_stale", tier2_failures)
            self.assertIn("Candidate background", candidate_path.read_text(encoding="utf-8"))
            candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            critic_block = _verification_block(verification)["citation_integrity_critic"]
            self.assertEqual(critic_block["manuscript_sha256"], candidate_hash)
            self.assertTrue(critic_block["sha256"])
            refreshed_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(refreshed_critic["manuscript_sha256"], candidate_hash)

    def test_qa_loop_step_candidate_verification_refreshes_citation_integrity_for_staged_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "Draft background~\\cite{Prior}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            candidate = original.replace("Draft background", "Candidate background")
            paper.write_text(original, encoding="utf-8")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{Prior, title={Prior Work}, author={Alice}, year={2024}}\n", encoding="utf-8")
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{Prior} Prior Work.\n", encoding="utf-8")
            support = artifact_path(root, "citation_support_review.json")
            support.write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "Draft background~\\cite{Prior}.",
                                "citation_keys": ["Prior"],
                                "support_status": "weakly_supported",
                                "evidence": [{"url": "https://example.test/prior"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            compile_report = artifact_path(root, "compile-report.json")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                citation_integrity_critic_path,
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5)
            stale_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(stale_critic["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())

            candidate_path = artifact_path(root, "paper.qa-loop-test.candidate.tex")
            candidate_path.write_text(candidate, encoding="utf-8")

            def fake_citation_review(cwd, **kwargs):
                refreshed = artifact_path(cwd, "citation_support_review.json")
                refreshed.write_text(
                    json.dumps(
                        {
                            "evidence_mode": "web",
                            "items": [
                                {
                                    "id": "s1",
                                    "sentence": "Candidate background~\\cite{Prior}.",
                                    "citation_keys": ["Prior"],
                                    "support_status": "supported",
                                    "evidence": [{"url": "https://example.test/prior"}],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return refreshed

            repair_payload = {
                "accepted": True,
                "committed": False,
                "candidate_path": str(candidate_path),
                "candidate_sha256": "sha256:" + hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
            }
            forced_plan_path = artifact_path(root, "qa-loop.plan.forced.json")
            forced_plan = {
                "schema_version": "qa-loop-plan/2",
                "session_id": state.session_id,
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            forced_plan_path.write_text(json.dumps(forced_plan), encoding="utf-8")
            from paperorchestra import quality_loop as quality_loop_module

            real_write_quality_loop_plan = quality_loop_module.write_quality_loop_plan
            plan_call_count = 0

            def forced_then_real_plan(cwd, *args, **kwargs):
                nonlocal plan_call_count
                plan_call_count += 1
                if plan_call_count == 1:
                    return forced_plan_path, forced_plan
                return real_write_quality_loop_plan(cwd, *args, **kwargs)

            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility):
                with patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                    with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_payload):
                        with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=fake_citation_review):
                            with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", side_effect=forced_then_real_plan):
                                result = run_qa_loop_step(
                                    root,
                                    MockProvider(),
                                    quality_mode="claim_safe",
                                    max_iterations=5,
                                    require_live_verification=False,
                                    require_compile=False,
                                    citation_evidence_mode="heuristic",
                                    citation_provider_name="mock",
                                )

            execution = result.payload
            candidate_state = execution.get("candidate_state") or {}
            candidate_failures = set((candidate_state.get("after") or {}).get("failing_codes") or [])
            self.assertNotIn("citation_critic_stale", candidate_failures)
            self.assertNotIn("citation_integrity_stale", candidate_failures)
            self.assertNotIn("rendered_reference_audit_stale", candidate_failures)
            original_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
            candidate_hash = hashlib.sha256(Path(candidate_state["manuscript_path"]).read_bytes()).hexdigest()
            candidate_critic = ((candidate_state.get("verification") or {}).get("citation_integrity") or {}).get("citation_integrity_critic") or {}
            self.assertEqual(candidate_critic.get("manuscript_sha256"), candidate_hash)
            restored_verification = execution.get("restored_current_verification") or {}
            top_level_verification = execution.get("verification") or {}
            self.assertEqual(top_level_verification, restored_verification)
            restored_critic = ((restored_verification.get("citation_integrity") or {}).get("citation_integrity_critic") or {})
            self.assertEqual(restored_critic.get("manuscript_sha256"), original_hash)
            top_level_critic = ((top_level_verification.get("citation_integrity") or {}).get("citation_integrity_critic") or {})
            self.assertEqual(top_level_critic.get("manuscript_sha256"), original_hash)
            refreshed_critic = json.loads(citation_integrity_critic_path(root).read_text(encoding="utf-8"))
            self.assertEqual(refreshed_critic["manuscript_sha256"], original_hash)

    def test_ralph_start_dry_run_satisfies_claim_safe_ralph_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence_root = root / "evidence"
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n",
                encoding="utf-8",
            )
            refs = artifact_path(root, "references.bib")
            refs.write_text(
                "@techreport{RFC9001, title={Using TLS to Secure QUIC}, author={Martin Thomson and Sean Turner}, year={2021}, url={https://www.rfc-editor.org/rfc/rfc9001}}\n",
                encoding="utf-8",
            )
            artifact_path(root, "paper.full.bbl").write_text("\\bibitem{RFC9001} Using TLS to Secure QUIC.\n", encoding="utf-8")
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "evidence_mode": "web",
                        "items": [
                            {
                                "id": "s1",
                                "sentence": "RFC 9001 describes how TLS secures QUIC~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "supported",
                                "evidence": [{"url": "https://www.rfc-editor.org/rfc/rfc9001"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.references_bib = str(refs)
            save_session(root, state)
            write_planning_artifacts(root)
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF-1.5\n")
            compile_report = artifact_path(root, "compile-report.json")
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            compile_report.write_text(
                json.dumps({"clean": True, "manuscript_sha256": manuscript_sha, "pdf_path": str(pdf), "pdf_exists": True, "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}),
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(pdf)
            save_session(root, state)
            from paperorchestra.citation_integrity import (
                write_citation_integrity_audit,
                write_citation_integrity_critic,
                write_rendered_reference_audit,
            )

            write_rendered_reference_audit(root, quality_mode="claim_safe")
            write_citation_integrity_audit(root, quality_mode="claim_safe")
            write_citation_integrity_critic(root, quality_mode="claim_safe")
            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility):
                with patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                    _, before = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
                    self.assertIn("ralph_handoff_missing", before["tiers"]["tier_2_claim_safety"]["failing_codes"])
                    old_cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        self.assertEqual(
                            cli_main(
                                [
                                    "ralph-start",
                                    "--dry-run",
                                    "--quality-mode",
                                    "claim_safe",
                                    "--max-iterations",
                                    "5",
                                    "--require-live-verification",
                                    "--evidence-root",
                                    str(evidence_root),
                                ]
                            ),
                            0,
                        )
                    finally:
                        os.chdir(old_cwd)
                    handoff = artifact_path(root, "ralph-handoff.json")
                    self.assertTrue(handoff.exists())
                    self.assertTrue((root / ".paper-orchestra" / "qa-loop-history.jsonl").exists())
                    _, after = write_quality_eval(root, quality_mode="claim_safe", max_iterations=5)
            tier2 = after["tiers"]["tier_2_claim_safety"]
            self.assertNotIn("ralph_handoff_missing", tier2["failing_codes"])
            self.assertTrue(after["source_artifacts"]["ralph_handoff_sha256"])
            self.assertEqual(tier2["checks"]["ralph_evidence"]["status"], "pass")

    def test_operator_feedback_explicit_rejection_is_human_needed_not_execution_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="Reject the current candidate because it should not be promoted.",
                suggested_action="Keep the current manuscript and request human follow-up.",
            )
            feedback_path = root / "operator-feedback-reject.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "reject_candidate_with_reason",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "Reject the current candidate because it should not be promoted.",
                                "suggested_action": "Keep the current manuscript and request human follow-up.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:same", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=AssertionError("reject must not rewrite")):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(execution["promotion_reason"], "operator_rejected_candidate")
            self.assertEqual(execution["candidate_rollback"]["reason"], "operator_rejected_candidate")
            self.assertEqual(execution["actionable_failure"]["category"], "operator_rejected_candidate")
            self.assertEqual(execution["actionable_failure"]["code"], "operator_rejected_candidate")
            self.assertEqual(execution["actionable_failure"]["latest_gate_reasons"], [])
            self.assertEqual(execution["supervised_iteration_index"], 0)
            self.assertEqual(execution["attempts"], [])

    def test_operator_feedback_catastrophic_regression_threshold_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {"organization_and_writing": {"score": 70}}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def run_with_scores(overall_after: float, axis_after: float):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                candidate = artifact_path(root, f"candidate-{overall_after}-{axis_after}.tex")
                candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")
                def fake_refine(cwd, provider, **kwargs):
                    return [{"iteration": 1, "candidate_only": True, "candidate_path": str(candidate), "candidate_sha256": "x", "score_before": 70.0, "score_after": overall_after, "axis_scores_before": {"organization_and_writing": 70.0}, "axis_scores_after": {"organization_and_writing": axis_after}}]
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            _, at_boundary = run_with_scores(62.0, 55.0)
            self.assertEqual(at_boundary["promotion_status"], "promoted")
            _, beyond = run_with_scores(61.9, 55.0)
            self.assertEqual(beyond["promotion_status"], "rolled_back")
            self.assertIn("reviewer_catastrophic_regression", beyond["attempts"][-1]["gate_reasons"])

    def test_operator_feedback_failed_candidate_rolls_back_citation_support_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original_text = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n"
            paper.write_text(original_text, encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            support_path = paper.parent / "citation_support_review.json"
            original_support = {"schema": "citation-support-review/3", "marker": "original"}
            support_path.write_text(json.dumps(original_support), encoding="utf-8")
            reference_source = artifact_path(root, "references/C1/source.txt")
            reference_source.write_text("original source evidence", encoding="utf-8")
            reference_resolution = artifact_path(root, "references/C1/human-resolution.json")
            new_reference_source = artifact_path(root, "references/C2/nested/source.txt")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction needs a candidate change.",
                suggested_action="Add a candidate sentence.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction needs a candidate change.",
                                "suggested_action": "Add a candidate sentence.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(original_text.replace("Draft.", "Draft. Candidate sentence."), encoding="utf-8")
                return [{"iteration": 1, "accepted": True, "reason": "test"}]

            citation_write_count = {"value": 0}

            def fake_write_citation_review(cwd, *args, **kwargs):
                citation_write_count["value"] += 1
                if citation_write_count["value"] == 1:
                    support_path.write_text(json.dumps({"schema": "citation-support-review/3", "marker": "candidate"}), encoding="utf-8")
                    reference_source.write_text("candidate source evidence", encoding="utf-8")
                    reference_resolution.write_text(
                        json.dumps(
                            {
                                "schema": "citation-human-resolution/1",
                                "case": "C1",
                                "action": "provide_source_url",
                                "url": "https://publisher.example.org/candidate",
                            }
                        ),
                        encoding="utf-8",
                    )
                    new_reference_source.write_text("candidate-only nested source evidence", encoding="utf-8")
                return support_path

            candidate_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["new_candidate_blocker"]}},
            }
            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", side_effect=fake_write_citation_review):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", side_effect=[(root / "candidate-quality.json", candidate_eval), (root / "restored-quality.json", restored_eval)]):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", side_effect=[(root / "candidate-plan.json", {"verdict": "failed"}), (root / "restored-plan.json", {"verdict": "human_needed"})]):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(paper.read_text(encoding="utf-8"), original_text)
            self.assertEqual(json.loads(support_path.read_text(encoding="utf-8")), original_support)
            self.assertEqual(reference_source.read_text(encoding="utf-8"), "original source evidence")
            self.assertFalse(reference_resolution.exists())
            self.assertFalse(new_reference_source.exists())

    def test_operator_feedback_preserves_each_generated_candidate_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            shared_candidate = artifact_path(root, "shared-candidate.tex")
            call_count = {"value": 0}

            def fake_refine(cwd, provider, **kwargs):
                call_count["value"] += 1
                shared_candidate.write_text(
                    f"\\documentclass{{article}}\n\\begin{{document}}\n\\section{{Intro}}\nDraft. Contribution language attempt {call_count['value']}.\\end{{document}}\n",
                    encoding="utf-8",
                )
                return [{"iteration": 1, "candidate_path": str(shared_candidate), "candidate_sha256": "sha256:" + hashlib.sha256(shared_candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path, max_supervised_iterations=2)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            candidate_paths = [Path(attempt["candidate_path"]) for attempt in execution["attempts"]]
            self.assertEqual(len(candidate_paths), 2)
            self.assertNotEqual(candidate_paths[0], candidate_paths[1])
            self.assertIn("attempt 1", candidate_paths[0].read_text(encoding="utf-8"))
            self.assertIn("attempt 2", candidate_paths[1].read_text(encoding="utf-8"))

    def test_operator_feedback_attempt_surfaces_contract_regression_preservation_without_executor_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original_text = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\\end{document}\n"
            paper.write_text(original_text, encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            rejected = artifact_path(root, "paper.refined.iter-01.rejected-contract.tex")
            rejected.write_text("\\documentclass{article}\n\\begin{document}\nRegressed candidate.\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{
                    "iteration": 1,
                    "candidate_only": True,
                    "reason": "candidate_ready_without_generic_acceptance",
                    "candidate_path": str(paper),
                    "candidate_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "score_before": 70,
                    "score_after": 70,
                    "axis_scores_before": {},
                    "axis_scores_after": {},
                    "preserved_prior_after_contract_regression": True,
                    "rejected_candidate_path": str(rejected),
                    "contract_regression_issue_count": 2,
                }]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertEqual(execution["verdict"], "human_needed")
            attempt = execution["attempts"][0]
            self.assertTrue(attempt["preserved_prior_after_contract_regression"])
            self.assertEqual(attempt["rejected_candidate_path"], str(rejected))
            self.assertEqual(attempt["executor_failure_category"], "none")
            self.assertIn("contract_regression_preserved_prior", attempt["gate_reasons"])

    def test_operator_feedback_promotes_operator_execution_candidate_with_human_reviewable_new_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(), "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Unsupported claim remains.", suggested_action="Soften unsupported claim.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Unsupported claim remains.", "suggested_action": "Soften unsupported claim.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-manual-check.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Softened claim needing manual check.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            manual_check_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    _, first_execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(first_execution["promotion_status"], "rolled_back")
            self.assertEqual(first_execution["candidate_approval"]["status"], "human_needed_candidate_ready")
            self.assertEqual(first_execution["candidate_progress"]["new_codes"], ["citation_support_manual_check"])

            packet_path2, packet2 = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet2["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            approve_issue_id = derive_operator_issue_id(packet2["packet_sha256"], source_artifact_role="operator_feedback_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Manual-check candidate is approved by the operator.", suggested_action="Promote the human-reviewed candidate.")
            approve_feedback = root / "operator-feedback-approve.json"
            approve_feedback.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet2["packet_sha256"], "manuscript_sha256": packet2["manuscript_sha256"], "issues": [{"id": approve_issue_id, "source_artifact_role": "operator_feedback_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Manual-check candidate is approved by the operator.", "suggested_action": "Promote the human-reviewed candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            approve_imported, _ = import_operator_feedback(root, packet_path=packet_path2, feedback_path=approve_feedback, output_path=root / "operator-feedback-approve.imported.json")
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=approve_imported)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Softened claim needing manual check", paper.read_text(encoding="utf-8"))

    def test_operator_review_packet_freezes_mutable_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            mutable_plan = artifact_path(root, "qa-loop.plan.json")
            original_plan_text = mutable_plan.read_text(encoding="utf-8")

            packet_path, packet = build_operator_review_packet(
                root,
                output_path=root / "operator-feedback" / "operator-review-packet.cycle-1.json",
                review_scope="tex_only",
            )

            packet_snapshot_dir = packet_path.with_suffix(".artifacts").resolve()
            qa_plan_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "qa_loop_plan")
            frozen_plan = Path(qa_plan_record["path"]).resolve()
            self.assertEqual(packet_snapshot_dir, frozen_plan.parent)
            self.assertEqual(qa_plan_record["original_path"], str(mutable_plan.resolve()))
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            mutable_plan.write_text(json.dumps({"verdict": "failed"}), encoding="utf-8")
            self.assertEqual(frozen_plan.read_text(encoding="utf-8"), original_plan_text)

            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="qa_loop_plan",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="The frozen plan remains human-needed.",
                suggested_action="Continue supervised feedback.",
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
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The frozen plan remains human-needed.",
                                "suggested_action": "Continue supervised feedback.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            mutable_plan.write_text(original_plan_text, encoding="utf-8")
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["packet_sha256"], packet["packet_sha256"])

    def test_build_operator_review_packet_includes_operator_execution_after_current_human_needed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "manuscript_sha256_before": base_sha,
                        "promotion_status": "rolled_back",
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "base_manuscript_sha256": base_sha,
                        },
                        "attempts": [],
                    }
                ),
                encoding="utf-8",
            )

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")

            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("operator_feedback_execution", roles)
            self.assertIn("qa_loop_plan", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="verdict",
                target_section="Whole manuscript",
                rationale="Operator feedback remains at a human-needed gate.",
                suggested_action="Continue supervised operator review.",
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
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "verdict",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Operator feedback remains at a human-needed gate.",
                                "suggested_action": "Continue supervised operator review.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertTrue(imported_path.exists())
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")

    def test_operator_feedback_approval_uses_issue_source_when_candidate_sources_compete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "manuscript_hash": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                        "tiers": {
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_unsupported"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            wrong_candidate = artifact_path(root, "wrong-qa-candidate.tex")
            wrong_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nWrong QA candidate.\n\\end{document}\n", encoding="utf-8")
            right_candidate = artifact_path(root, "right-operator-candidate.tex")
            right_candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nRight operator candidate.\n\\end{document}\n", encoding="utf-8")
            qa_execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            qa_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(wrong_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(wrong_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(qa_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            qa_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(qa_execution_payload)
            qa_execution_path.write_text(json.dumps(qa_execution_payload), encoding="utf-8")
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_payload = {
                "schema_version": "operator-feedback-execution/1",
                "verdict": "human_needed",
                "promotion_status": "rolled_back",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(right_candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(right_candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(operator_execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-03T00:00:01Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_unsupported"],
                    "after_failing_codes": ["citation_support_manual_check"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            operator_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(operator_execution_payload)
            operator_execution_path.write_text(json.dumps(operator_execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            roles = {artifact["role"] for artifact in packet["artifacts"]}
            self.assertIn("qa_loop_execution", roles)
            self.assertIn("operator_feedback_execution", roles)
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_approval",
                target_section="Whole manuscript",
                rationale="Approve the operator-generated candidate, not the stale QA-loop candidate.",
                suggested_action="Promote the operator-feedback candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "Approve the operator-generated candidate, not the stale QA-loop candidate.",
                                "suggested_action": "Promote the operator-feedback candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            manual_check_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", manual_check_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertIn("Right operator candidate", paper.read_text(encoding="utf-8"))
            self.assertNotIn("Wrong QA candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_approval_accepts_nested_operator_candidate_source_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBase draft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            candidate = artifact_path(root, "nested-operator-candidate.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nNested operator candidate.\n\\end{document}\n",
                encoding="utf-8",
            )
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            embedded_source_path = root / ".paper-orchestra" / "qa-loop-execution.iter-02.json"
            source_execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(embedded_source_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-05-04T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_insufficient_evidence"],
                    "after_failing_codes": [],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            source_execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(source_execution_payload)
            operator_execution_path = artifact_path(root, "operator_feedback.execution.json")
            operator_execution_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback-execution/1",
                        "verdict": "human_needed",
                        "promotion_status": "rolled_back",
                        "candidate_branch": "approve_existing_candidate",
                        "candidate_result": {
                            "candidate_path": str(candidate),
                            "candidate_sha256": candidate_sha,
                            "candidate_approval": source_execution_payload["candidate_approval"],
                            "candidate_progress": source_execution_payload["candidate_progress"],
                            "candidate_state": source_execution_payload["candidate_state"],
                            "source_execution": source_execution_payload,
                            "executor_source_role": "qa_loop_execution",
                            "executor_failure_category": "none",
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            operator_record = next(artifact for artifact in packet["artifacts"] if artifact["role"] == "operator_feedback_execution")
            self.assertNotEqual(str(embedded_source_path.resolve()), str(Path(operator_record["path"]).resolve()))
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="operator_feedback_execution",
                source_item_key="candidate_result.candidate_approval",
                target_section="Whole manuscript",
                rationale="The nested operator candidate is approved by the operator.",
                suggested_action="Promote the nested operator candidate.",
            )
            feedback_path = root / "operator-feedback-approve.json"
            feedback_path.write_text(
                json.dumps(
                    {
                        "schema_version": "operator-feedback/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "intent": "approve_existing_candidate",
                        "packet_sha256": packet["packet_sha256"],
                        "manuscript_sha256": packet["manuscript_sha256"],
                        "issues": [
                            {
                                "id": issue_id,
                                "source_artifact_role": "operator_feedback_execution",
                                "source_item_key": "candidate_result.candidate_approval",
                                "target_section": "Whole manuscript",
                                "severity": "major",
                                "rationale": "The nested operator candidate is approved by the operator.",
                                "suggested_action": "Promote the nested operator candidate.",
                                "authority_class": "author_feedback",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass"},
                },
            }
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, approved = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(approved["promotion_status"], "promoted")
            self.assertEqual(approved["candidate_result"]["executor_source_role"], "operator_feedback_execution")
            self.assertIn("Nested operator candidate", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_refreshes_figure_review_for_candidate_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            artifact_path(root, "quality-eval.json").write_text(json.dumps({"schema_version": "quality-eval/1", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            # Simulate the live-smoke path: a figure-placement review exists for
            # the pre-feedback manuscript. Candidate staging changes the
            # manuscript hash, so operator verification must refresh this review
            # before quality-eval runs; otherwise Tier 0 reports
            # figure_placement_review_stale and rejects a valid candidate.
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(paper.read_bytes()).hexdigest())
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-with-figure-refresh.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "promoted")
            attempt = execution["attempts"][0]
            self.assertNotIn("tier0_failed", attempt["gate_reasons"])
            figure_block = attempt["verification"]["figure_placement_review"]
            self.assertEqual(Path(figure_block["path"]).resolve(), stale_figure_path.resolve())
            self.assertNotEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())
            self.assertEqual(figure_block["manuscript_sha256"], hashlib.sha256(candidate.read_bytes()).hexdigest())

    def test_operator_feedback_promotes_existing_candidate_with_continue_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            artifact_path(root, "quality-eval.json").write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "session_id": state.session_id,
                        "mode": "claim_safe",
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass"},
                            "tier_1_structural": {"status": "pass"},
                            "tier_2_claim_safety": {
                                "status": "fail",
                                "failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate improvement.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {"schema_version": "qa-loop-execution/1", "verdict": "human_needed", "candidate_approval": {"status": "human_needed_candidate_ready", "candidate_path": str(candidate), "candidate_sha256": candidate_sha, "base_manuscript_sha256": base_sha, "source_execution_path": str(execution_path), "source_execution_sha256": "pending_until_execution_write", "created_at": "2026-04-27T00:00:00Z"}, "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_critic_failed"], "after_failing_codes": []}, "candidate_state": {"verification": {"validate_current": {"ok": True}}}}
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is ready for supervised approval.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is ready for supervised approval.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass"}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertEqual(execution["post_promotion_qa_verdict"], "continue")
            self.assertIn("Candidate improvement", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_promotes_existing_candidate_with_reduced_citation_issue_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Candidate reduces citation issue count.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "after_failing_codes": ["citation_support_manual_check", "citation_support_weak"],
                    "before_citation_issue_count": 22,
                    "after_citation_issue_count": 20,
                    "citation_issue_delta": -2,
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate reduces citation issue count.", suggested_action="Approve the ready candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate reduces citation issue count.", "suggested_action": "Approve the ready candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_manual_check"]}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "promoted")
            self.assertNotIn("active_blocker_metric_progress_missing", execution["attempts"][0]["gate_reasons"])
            self.assertIn("Candidate reduces citation issue count", paper.read_text(encoding="utf-8"))

    def test_operator_feedback_rejects_existing_candidate_without_resolved_active_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Same blocker candidate.\n\\end{document}\n", encoding="utf-8")
            candidate_sha = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
            base_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": candidate_sha,
                    "base_manuscript_sha256": base_sha,
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {
                    "forward_progress": True,
                    "before_failing_codes": ["citation_support_critic_failed"],
                    "after_failing_codes": ["citation_support_critic_failed"],
                },
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate does not resolve the blocker.", suggested_action="Reject same-blocker candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate does not resolve the blocker.", "suggested_action": "Reject same-blocker candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("resolved active blockers", execution["error"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_operator_feedback_approval_requires_full_candidate_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nBound candidate.\\end{document}\n", encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    # Missing source_execution_sha256 and created_at must fail closed.
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="Candidate is missing binding evidence.", suggested_action="Approve only if binding is complete.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "Candidate is missing binding evidence.", "suggested_action": "Approve only if binding is complete.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("missing candidate_approval", execution["error"])
            self.assertEqual(hashlib.sha256(paper.read_bytes()).hexdigest(), hashlib.sha256("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n".encode("utf-8")).hexdigest())

    def test_operator_feedback_rejects_noop_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root, verdict="human_needed")
            candidate = artifact_path(root, "paper.candidate.tex")
            candidate.write_text(original, encoding="utf-8")
            execution_path = root / ".paper-orchestra" / "qa-loop-execution.iter-01.json"
            execution_payload = {
                "schema_version": "qa-loop-execution/1",
                "verdict": "human_needed",
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_path": str(candidate),
                    "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    "base_manuscript_sha256": "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "source_execution_path": str(execution_path),
                    "source_execution_sha256": "pending_until_execution_write",
                    "created_at": "2026-04-27T00:00:00Z",
                },
                "candidate_progress": {"forward_progress": True, "before_failing_codes": ["citation_support_weak"], "after_failing_codes": []},
                "candidate_state": {"verification": {"validate_current": {"ok": True}}},
            }
            execution_payload["candidate_approval"]["source_execution_sha256"] = self._execution_source_sha(execution_payload)
            execution_path.write_text(json.dumps(execution_payload), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="qa_loop_execution", source_item_key="candidate_approval", target_section="Whole manuscript", rationale="No-op candidate should not be promoted.", suggested_action="Reject the no-op candidate.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "qa_loop_execution", "source_item_key": "candidate_approval", "target_section": "Whole manuscript", "severity": "major", "rationale": "No-op candidate should not be promoted.", "suggested_action": "Reject the no-op candidate.", "authority_class": "author_feedback"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "pass", "failing_codes": []}}}
            with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                    with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                        with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                            with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)
            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("no_textual_change", execution["attempts"][-1]["gate_reasons"])
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "preexisting_candidate")
            failure = execution["actionable_failure"]
            self.assertEqual(failure["category"], "operator_candidate_failed_hard_gate")
            self.assertEqual(failure["code"], "operator_candidate_failed_hard_gate")
            self.assertIn("no_textual_change", failure["latest_gate_reasons"])
            self.assertIn("executor_returned_identical_content", failure["latest_gate_reasons"])
            self.assertNotIn("blocked_candidate_progress", failure)
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertEqual(incorporation["actionable_failure"]["latest_gate_reasons"], failure["latest_gate_reasons"])
            self.assertNotIn("blocked_candidate_progress", incorporation["actionable_failure"])
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            history_failure = history[-1]["actionable_failure"]
            self.assertEqual(history_failure["category"], "operator_candidate_failed_hard_gate")
            self.assertIn("no_textual_change", history_failure["latest_gate_reasons"])
            self.assertNotIn("blocked_candidate_progress", history_failure)
            self.assertNotIn("Draft", json.dumps(history_failure))
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_import_operator_feedback_accepts_action_kind_intent_and_rejects_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="Needs direction.", suggested_action="Add direction.")
            base_issue = {"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "Needs direction.", "suggested_action": "Add direction.", "authority_class": "prose_rewrite"}
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            _, imported = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            self.assertEqual(imported["intent"], "generate_new_operator_candidate")
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "approve_existing_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{**base_issue, "action_kind": "generate_new_operator_candidate"}]}), encoding="utf-8")
            with self.assertRaises(ContractError):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path, output_path=root / "conflict.json")

    def test_operator_feedback_blocks_only_new_tier2_claim_safety_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 70, "axis_scores": {}, "summary": {"weaknesses": [], "top_improvements": []}, "questions": [], "penalties": []}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            base_eval_path = artifact_path(root, "quality-eval.json")
            base_eval_path.write_text(json.dumps({"schema_version": "quality-eval/1", "session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["existing_claim_issue"]}}}), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(packet["packet_sha256"], source_artifact_role="paper_full_tex", source_item_key="Intro:p1", target_section="Intro", rationale="The contribution paragraph is missing.", suggested_action="Add contribution language.")
            feedback_path = root / "operator-feedback.json"
            feedback_path.write_text(json.dumps({"schema_version": "operator-feedback/1", "source": "codex_operator", "not_independent_human_review": True, "intent": "generate_new_operator_candidate", "packet_sha256": packet["packet_sha256"], "manuscript_sha256": packet["manuscript_sha256"], "issues": [{"id": issue_id, "source_artifact_role": "paper_full_tex", "source_item_key": "Intro:p1", "target_section": "Intro", "severity": "major", "rationale": "The contribution paragraph is missing.", "suggested_action": "Add contribution language.", "authority_class": "prose_rewrite"}]}), encoding="utf-8")
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-tier2.tex")
            candidate.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Contribution language.\n\\end{document}\n", encoding="utf-8")

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "candidate_path": str(candidate), "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(), "score_before": 70, "score_after": 70, "axis_scores_before": {}, "axis_scores_after": {}}]

            def run_with_codes(codes):
                paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n", encoding="utf-8")
                quality_eval = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {"tier_0_preconditions": {"status": "pass"}, "tier_1_structural": {"status": "pass"}, "tier_2_claim_safety": {"status": "fail" if codes else "pass", "failing_codes": codes}}}
                with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                    with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                            with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "continue"})):
                                        return apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)[1]

            existing_only = run_with_codes(["existing_claim_issue"])
            self.assertEqual(existing_only["promotion_status"], "rolled_back")
            self.assertIn("active_blocker_metric_progress_missing", existing_only["attempts"][-1]["gate_reasons"])
            self.assertEqual(existing_only["attempts"][-1]["resolved_active_failures"], [])
            resolved = run_with_codes([])
            self.assertEqual(resolved["promotion_status"], "promoted")
            self.assertEqual(resolved["attempts"][-1]["resolved_active_failures"], ["existing_claim_issue"])
            with_new = run_with_codes(["existing_claim_issue", "new_claim_issue"])
            self.assertEqual(with_new["promotion_status"], "rolled_back")
            self.assertIn("tier2_claim_safety_new_failures", with_new["attempts"][-1]["gate_reasons"])
            self.assertIn("active_blocker_metric_progress_missing", with_new["attempts"][-1]["gate_reasons"])
            self.assertEqual(with_new["attempts"][-1]["new_tier2_failures"], ["new_claim_issue"])
            self.assertEqual(with_new["actionable_failure"]["new_tier2_failures"], ["new_claim_issue"])
            self.assertIn("tier2_claim_safety_new_failures", with_new["actionable_failure"]["latest_gate_reasons"])

    def test_operator_feedback_reports_progress_blocked_by_new_tier2_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            review = review_path(root, "review.latest.json")
            review.write_text(
                json.dumps(
                    {
                        "overall_score": 70,
                        "axis_scores": {},
                        "summary": {"weaknesses": [], "top_improvements": []},
                        "questions": [],
                        "penalties": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)
            base_quality = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_weak", "critical_unsupported_citation"],
                        "checks": {
                            "citation_support_critic": {"weakly_supported_count": 5},
                            "citation_quality_gate": {"counts": {"critical_unsupported_count": 1}},
                        },
                    },
                },
            }
            artifact_path(root, "quality-eval.json").write_text(json.dumps(base_quality), encoding="utf-8")
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="Citation repair needs a local edit.",
                suggested_action="Make the local citation repair without adding source-obligation failures.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "Citation repair needs a local edit.",
                                "suggested_action": "Make the local citation repair without adding source-obligation failures.",
                                "authority_class": "citation_support",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            candidate = artifact_path(root, "candidate-progress-blocked.tex")
            candidate.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft. Citation repair.\n\\end{document}\n",
                encoding="utf-8",
            )

            candidate_quality = {
                "session_id": state.session_id,
                "mode": "claim_safe",
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_weak", "source_obligation_missing"],
                        "checks": {
                            "citation_support_critic": {"weakly_supported_count": 3},
                            "citation_quality_gate": {"counts": {"critical_unsupported_count": 0}},
                            "source_obligations": {"unsatisfied": [{"id": "synthetic-source-obligation"}]},
                        },
                    },
                },
            }

            def fake_refine(cwd, provider, **kwargs):
                return [
                    {
                        "iteration": 1,
                        "candidate_path": str(candidate),
                        "candidate_sha256": "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "score_before": 70,
                        "score_after": 70,
                        "axis_scores_before": {},
                        "axis_scores_after": {},
                    }
                ]

            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "quality.json", candidate_quality)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "plan.json", {"verdict": "human_needed"})):
                                    _, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertEqual(execution["promotion_status"], "rolled_back")
            self.assertIn("tier2_claim_safety_new_failures", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["resolved_active_failures"], ["critical_unsupported_citation"])
            failure = execution["actionable_failure"]
            self.assertEqual(failure["latest_gate_reasons"], ["tier2_claim_safety_new_failures"])
            self.assertEqual(failure["new_tier2_failures"], ["source_obligation_missing"])
            self.assertEqual(failure["resolved_active_failures"], ["critical_unsupported_citation"])
            self.assertIn("citation_support_weak", failure["candidate_active_failures"])
            self.assertIn("source_obligation_missing", failure["candidate_active_failures"])
            self.assertEqual(failure["base_active_failures"], ["citation_support_weak", "critical_unsupported_citation"])
            self.assertEqual(failure["executor_failure_category"], "none")
            progress = failure["blocked_candidate_progress"]
            self.assertLessEqual(
                set(progress),
                {
                    "kind",
                    "blocking_gate_reasons",
                    "new_tier2_failures",
                    "resolved_active_failures",
                    "metric_improvements",
                    "metric_regressions",
                    "base_total",
                    "candidate_total",
                    "total_improved",
                    "recommended_next_focus",
                },
            )
            self.assertEqual(progress["kind"], "active_metric_improved_but_blocked")
            self.assertEqual(progress["blocking_gate_reasons"], ["tier2_claim_safety_new_failures"])
            self.assertEqual(progress["new_tier2_failures"], ["source_obligation_missing"])
            self.assertEqual(progress["resolved_active_failures"], ["critical_unsupported_citation"])
            self.assertEqual(progress["base_total"], 6)
            self.assertEqual(progress["candidate_total"], 3)
            self.assertTrue(progress["total_improved"])
            self.assertEqual(progress["metric_regressions"], [])
            self.assertEqual(
                progress["metric_improvements"],
                [
                    {"code": "citation_support_weak", "before": 5, "after": 3, "delta": -2},
                    {"code": "critical_unsupported_citation", "before": 1, "after": 0, "delta": -1},
                ],
            )
            serialized_failure = json.dumps(failure)
            self.assertNotIn("candidate_path", serialized_failure)
            self.assertNotIn("candidate_text", serialized_failure)
            self.assertNotIn(str(root), serialized_failure)
            self.assertNotIn(candidate.name, serialized_failure)
            self.assertNotIn("Draft. Citation repair", serialized_failure)
            self.assertNotIn("synthetic-source-obligation", serialized_failure)
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertEqual(incorporation["actionable_failure"]["blocked_candidate_progress"], progress)
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["actionable_failure"]["blocked_candidate_progress"], progress)

    def test_operator_feedback_hard_gate_rejects_active_tier2_metric_regression(self) -> None:
        from paperorchestra.operator_feedback import _candidate_hard_gate

        base_quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_weak", "citation_support_manual_check", "high_risk_uncited_claim"],
                    "checks": {
                        "citation_support_critic": {
                            "weakly_supported_count": 3,
                            "needs_manual_check_count": 3,
                        },
                        "high_risk_claim_sweep": {"item_count": 39},
                    },
                }
            }
        }
        candidate_quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_manual_check", "high_risk_uncited_claim"],
                    "checks": {
                        "citation_support_critic": {
                            "weakly_supported_count": 0,
                            "needs_manual_check_count": 7,
                        },
                        "high_risk_claim_sweep": {"item_count": 41},
                    },
                }
            }
        }

        ok, reasons = _candidate_hard_gate(
            validation_payload={"ok": True},
            compile_payload={"ok": True},
            quality_eval=candidate_quality_eval,
            base_quality_eval=base_quality_eval,
            quality_mode="claim_safe",
            incorporation=[{"status": "reflected"}],
            candidate_result={"candidate_progress": {"forward_progress": True, "citation_issue_delta": -3}},
            require_issue_progress=True,
            manuscript_changed=True,
            new_tier2_failures=[],
            base_active_failures=["citation_support_weak", "citation_support_manual_check", "high_risk_uncited_claim"],
            resolved_active_failures=["citation_support_weak"],
        )

        self.assertFalse(ok)
        self.assertIn("active_tier2_metric_regression", reasons)

    def test_operator_feedback_hard_gate_allows_metric_progress_without_code_resolution(self) -> None:
        from paperorchestra.operator_feedback import _candidate_hard_gate

        base_quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_manual_check", "high_risk_uncited_claim"],
                    "checks": {
                        "citation_support_critic": {"needs_manual_check_count": 7},
                        "high_risk_claim_sweep": {"item_count": 41},
                    },
                }
            }
        }
        candidate_quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_manual_check", "high_risk_uncited_claim"],
                    "checks": {
                        "citation_support_critic": {"needs_manual_check_count": 5},
                        "high_risk_claim_sweep": {"item_count": 39},
                    },
                }
            }
        }

        ok, reasons = _candidate_hard_gate(
            validation_payload={"ok": True},
            compile_payload={"ok": True},
            quality_eval=candidate_quality_eval,
            base_quality_eval=base_quality_eval,
            quality_mode="claim_safe",
            incorporation=[{"status": "reflected"}],
            candidate_result={"candidate_progress": {"forward_progress": True}},
            require_issue_progress=True,
            manuscript_changed=True,
            new_tier2_failures=[],
            base_active_failures=["citation_support_manual_check", "high_risk_uncited_claim"],
            resolved_active_failures=[],
        )

        self.assertTrue(ok)
        self.assertNotIn("active_tier2_metric_regression", reasons)
        self.assertNotIn("active_blocker_metric_progress_missing", reasons)

    def test_operator_feedback_hard_gate_rejects_no_code_or_metric_progress(self) -> None:
        from paperorchestra.operator_feedback import _candidate_hard_gate

        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "failing_codes": ["citation_support_manual_check"],
                    "checks": {"citation_support_critic": {"needs_manual_check_count": 7}},
                }
            }
        }

        ok, reasons = _candidate_hard_gate(
            validation_payload={"ok": True},
            compile_payload={"ok": True},
            quality_eval=quality_eval,
            base_quality_eval=quality_eval,
            quality_mode="claim_safe",
            incorporation=[{"status": "reflected"}],
            candidate_result={"candidate_progress": {"forward_progress": True}},
            require_issue_progress=True,
            manuscript_changed=True,
            new_tier2_failures=[],
            base_active_failures=["citation_support_manual_check"],
            resolved_active_failures=[],
        )

        self.assertFalse(ok)
        self.assertIn("active_blocker_metric_progress_missing", reasons)

    def test_operator_feedback_human_review_filter_rejects_metric_progress_missing(self) -> None:
        from paperorchestra.operator_feedback import _candidate_attempt_ready_for_human_review

        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.tex"
            candidate.write_text("candidate", encoding="utf-8")
            base_attempt = {
                "candidate_path": str(candidate),
                "resolved_active_failures": ["citation_support_manual_check"],
                "new_tier2_failures": [],
            }

            allowed = dict(base_attempt, gate_reasons=[])
            self.assertTrue(_candidate_attempt_ready_for_human_review(allowed))

            blocked_new_reason = dict(base_attempt, gate_reasons=["active_blocker_metric_progress_missing"])
            self.assertFalse(_candidate_attempt_ready_for_human_review(blocked_new_reason))

            blocked_historical_reason = dict(base_attempt, gate_reasons=["active_blocker_progress_missing"])
            self.assertFalse(_candidate_attempt_ready_for_human_review(blocked_historical_reason))

    def test_operator_feedback_rollback_records_restored_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The introduction remains unchanged after operator review.",
                suggested_action="Add a concrete contribution paragraph.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The introduction remains unchanged after operator review.",
                                "suggested_action": "Add a concrete contribution paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def fake_refine(cwd, provider, **kwargs):
                return [{"iteration": 1, "accepted": True, "reason": "no textual change"}]

            candidate_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:candidate", "tiers": {}}
            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=fake_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch(
                                "paperorchestra.operator_feedback.write_quality_eval",
                                side_effect=[(root / "candidate-quality.json", candidate_eval), (root / "restored-quality.json", restored_eval)],
                            ):
                                with patch(
                                    "paperorchestra.operator_feedback.write_quality_loop_plan",
                                    side_effect=[(root / "candidate-plan.json", {"verdict": "failed"}), (root / "restored-plan.json", {"verdict": "human_needed"})],
                                ):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "human_needed")
            self.assertEqual(execution["verification"]["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(execution["candidate_rollback"]["restored_verification"]["qa_loop_plan"]["verdict"], "human_needed")
            self.assertIn("executor_returned_identical_content", execution["attempts"][-1]["gate_reasons"])
            self.assertEqual(execution["attempts"][-1]["executor_environment"], "in_process")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "none")
            incorporation = json.loads(Path(execution["incorporation_report"]).read_text(encoding="utf-8"))
            self.assertIn(incorporation["issues"][0]["status"], {"not_reflected", "needs_author_decision"})
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])

    def test_operator_feedback_exception_rollback_records_restored_verification_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            self._write_terminal_human_needed_plan(root)

            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The supervised writer crashes after making a candidate change.",
                suggested_action="Attempt a safe introduction rewrite.",
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
                                "source_artifact_role": "paper_full_tex",
                                "source_item_key": "Intro:p1",
                                "target_section": "Intro",
                                "severity": "major",
                                "rationale": "The supervised writer crashes after making a candidate change.",
                                "suggested_action": "Attempt a safe introduction rewrite.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

            def crashing_refine(cwd, provider, **kwargs):
                target = Path(load_session(cwd).artifacts.paper_full_tex)
                target.write_text(target.read_text(encoding="utf-8") + "\nBAD CANDIDATE\n", encoding="utf-8")
                raise RuntimeError("boom")

            restored_eval = {"session_id": state.session_id, "mode": "claim_safe", "manuscript_hash": "sha256:restored", "tiers": {}}
            with patch("paperorchestra.operator_feedback.refine_current_paper", side_effect=crashing_refine):
                with patch("paperorchestra.operator_feedback.write_section_review", return_value=root / "section.json"):
                    with patch("paperorchestra.operator_feedback.write_citation_support_review", return_value=root / "citation.json"):
                        with patch("paperorchestra.operator_feedback.review_current_paper", return_value=root / "review.json"):
                            with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "restored-quality.json", restored_eval)):
                                with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "restored-plan.json", {"verdict": "human_needed"})):
                                    execution_path, execution = apply_operator_feedback(root, MockProvider(), imported_feedback_path=imported_path)

            self.assertTrue(execution_path.exists())
            self.assertEqual(execution["verdict"], "execution_error")
            self.assertEqual(execution["attempts"][-1]["executor_failure_category"], "unexpected_exception")
            self.assertTrue(execution["attempts"][-1]["executor_trace_artifact"])
            self.assertTrue(Path(execution["attempts"][-1]["executor_trace_artifact"]).exists())
            self.assertIn("executor_crashed", execution["attempts"][-1]["gate_reasons"])
            self.assertNotIn("BAD CANDIDATE", paper.read_text(encoding="utf-8"))
            restored = execution["candidate_rollback"]["restored_verification"]
            self.assertEqual(restored["qa_loop_plan"]["path"], str(root / "restored-plan.json"))
            self.assertEqual(restored["qa_loop_plan"]["verdict"], "human_needed")
            history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(history[-1]["event_type"], "operator_feedback_cycle")
            self.assertEqual(history[-1]["verdict"], "execution_error")
            self.assertEqual(history[-1]["plan_path"], str(root / "restored-plan.json"))
            self.assertFalse(history[-1]["consumes_budget"])
            self.assertNotIn("execution_error", history[-1])
            self.assertEqual(history[-1]["actionable_failure"]["category"], "operator_execution_error")
            self.assertEqual(history[-1]["actionable_failure"]["code"], "operator_executor_crashed")
            self.assertEqual(history[-1]["actionable_failure"]["executor_failure_category"], "unexpected_exception")
            self.assertNotIn("boom", json.dumps(history[-1]["actionable_failure"]))

    def test_qa_loop_step_cli_passes_citation_provider_settings(self) -> None:
        class Result:
            path = Path("execution.json")
            payload = {"verdict": "continue"}
            exit_code = 10

        stdout = io.StringIO()
        with patch("paperorchestra.cli.run_qa_loop_step", return_value=Result()) as runner:
            with contextlib.redirect_stdout(stdout):
                code = cli_main(
                    [
                        "qa-loop-step",
                        "--citation-evidence-mode",
                        "model",
                        "--provider",
                        "shell",
                        "--provider-command",
                        '["codex","exec"]',
                        "--quality-eval",
                        "quality.custom.json",
                        "--qa-loop-plan",
                        "plan.custom.json",
                        "--citation-support-review",
                        "citation.custom.json",
                    ]
                )

        self.assertEqual(code, 10)
        self.assertEqual(runner.call_args.kwargs["citation_provider_name"], "shell")
        self.assertEqual(runner.call_args.kwargs["citation_provider_command"], '["codex","exec"]')
        self.assertEqual(runner.call_args.kwargs["quality_eval_input_path"], "quality.custom.json")
        self.assertEqual(runner.call_args.kwargs["qa_loop_plan_input_path"], "plan.custom.json")
        self.assertEqual(runner.call_args.kwargs["citation_support_review_path"], "citation.custom.json")

    def test_candidate_apply_promotes_author_approved_candidate_to_session_manuscript(self) -> None:
        from paperorchestra.candidate_commands import candidate_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            editable = root / "paper" / "main.tex"
            editable.parent.mkdir()
            editable.write_text("OLD", encoding="utf-8")
            state.artifacts.paper_full_tex = str(editable)
            save_session(root, state)
            candidate = artifact_path(root, "paper.citation-repair.approval-test.candidate.tex")
            candidate.write_text("NEW", encoding="utf-8")

            with patch("paperorchestra.candidate_commands.record_current_validation_report", return_value=(root / "validation.json", {"ok": True})):
                with patch("paperorchestra.candidate_commands.compile_current_paper", return_value=root / "paper.pdf"):
                    result = candidate_apply(root, candidate.name, as_author_approved=True)

            promoted_state = load_session(root)
            canonical = artifact_path(root, "paper.full.tex")
            self.assertEqual(result["status"], "applied")
            self.assertEqual(editable.read_text(encoding="utf-8"), "NEW")
            self.assertEqual(canonical.read_text(encoding="utf-8"), "NEW")
            self.assertEqual(promoted_state.artifacts.paper_full_tex, str(canonical))
            self.assertEqual(result["validation"]["ok"], True)
            self.assertEqual(result["compile"]["ok"], True)

    def test_candidate_list_and_diff_resolve_candidate_files(self) -> None:
        from paperorchestra.candidate_commands import candidate_diff, candidate_list

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("OLD\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            candidate = artifact_path(root, "paper.citation-repair.approval-test.candidate.tex")
            candidate.write_text("NEW\n", encoding="utf-8")

            listing = candidate_list(root)
            diff = candidate_diff(root, candidate.name)

        self.assertEqual([item["filename"] for item in listing["candidates"]], [candidate.name])
        self.assertIn("-OLD", diff)
        self.assertIn("+NEW", diff)

    def test_candidate_cli_routes_apply_and_reject_commands(self) -> None:
        stdout = io.StringIO()
        with patch("paperorchestra.cli.candidate_apply", return_value={"status": "applied"}) as apply:
            with contextlib.redirect_stdout(stdout):
                code = cli_main(["candidate-apply", "cand-1", "--as-author-approved"])

        self.assertEqual(code, 0)
        self.assertEqual(apply.call_args.args[1], "cand-1")
        self.assertTrue(apply.call_args.kwargs["as_author_approved"])

        stdout = io.StringIO()
        with patch("paperorchestra.cli.candidate_reject", return_value={"status": "rejected"}) as reject:
            with contextlib.redirect_stdout(stdout):
                code = cli_main(["candidate-reject", "cand-1", "--reason", "not good enough"])

        self.assertEqual(code, 0)
        self.assertEqual(reject.call_args.args[1], "cand-1")
        self.assertEqual(reject.call_args.kwargs["reason"], "not good enough")

    def test_qa_loop_step_model_evidence_defaults_to_shell_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_review_missing"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_review_missing", "automation": "automatic"}],
            }
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.get_citation_support_provider", return_value=None) as provider_factory:
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", return_value=root / "citation.json"):
                                run_qa_loop_step(root, MockProvider(), citation_evidence_mode="model")

            self.assertEqual(provider_factory.call_args.args[0], "shell")

    def test_repair_citation_claims_restores_validation_pointer_on_compile_reject(self) -> None:
        class RepairProvider(MockProvider):
            def __init__(self, latex: str):
                self.latex = latex

            def complete(self, request: CompletionRequest) -> str:
                return "```latex\n" + self.latex + "\n```"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@techreport{RFC9001,\n"
                "  title = {Using {TLS} to Secure {QUIC}},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021},\n"
                "  url = {https://www.rfc-editor.org/rfc/rfc9001}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper = artifact_path(root, "paper.full.tex")
            original = (
                "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\n"
                "QUIC uses TLS~\\cite{RFC9001}.\n"
                "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
            )
            paper.write_text(original, encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            previous_validation, _ = record_current_validation_report(root, name="validation.previous.json")
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "QUIC uses TLS~\\cite{RFC9001}.",
                                "citation_keys": ["RFC9001"],
                                "support_status": "weakly_supported",
                                "risk": "medium",
                                "suggested_fix": "Soften.",
                            }
                        ],
                        "summary": {"weakly_supported": 1},
                    }
                ),
                encoding="utf-8",
            )
            provider = RepairProvider(original)

            with patch("paperorchestra.ralph_bridge_repair.compile_current_paper", side_effect=RuntimeError("compile down")):
                result = repair_citation_claims(root, provider, citation_review_path=review_path, require_compile=True)

            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "compile_failed")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)
            restored_state = load_session(root)
            self.assertEqual(restored_state.artifacts.latest_validation_json, str(previous_validation))
            self.assertIsNone(restored_state.artifacts.latest_compile_report_json)
            self.assertIsNone(restored_state.artifacts.compiled_pdf)

    def test_qa_loop_step_rolls_back_candidate_on_verification_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            quality_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", quality_eval)):
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)):
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=RuntimeError("critic down")):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 40)
            self.assertEqual(result.payload["verdict"], "execution_error")
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_qa_loop_step_commits_forward_progress_candidate_with_human_reviewable_residuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": [
                            "citation_support_insufficient_evidence",
                            "citation_support_weak",
                        ],
                    }
                },
            }
            candidate_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_weak"],
                    }
                },
            }
            restored_eval = before_eval
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            candidate_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            restored_plan = before_plan
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"insufficient_evidence": 1, "weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", candidate_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", candidate_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                            {"weakly_supported": 1},
                            {"insufficient_evidence": 1, "weakly_supported": 1},
                        ],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 10)
            self.assertEqual(result.payload["verdict"], "continue")
            self.assertNotIn("candidate_approval", result.payload)
            committed_candidate_path = Path(result.payload["candidate_auto_commit"]["candidate_path"])
            self.assertNotEqual(committed_candidate_path.resolve(), Path(repair_result["candidate_path"]).resolve())
            self.assertEqual(
                result.payload["candidate_auto_commit"]["candidate_sha256"],
                "sha256:" + hashlib.sha256(committed_candidate_path.read_bytes()).hexdigest(),
            )
            Path(repair_result["candidate_path"]).write_text("mutated volatile candidate", encoding="utf-8")
            self.assertEqual(committed_candidate_path.read_text(encoding="utf-8"), candidate)
            self.assertEqual(result.payload["candidate_auto_commit"]["status"], "committed_for_continued_qa")
            self.assertEqual(result.payload["candidate_auto_commit"]["residual_citation_failures"], ["citation_support_weak"])
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_insufficient_evidence"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], ["citation_support_weak"])
            self.assertNotIn("restored_current_state", result.payload)
            self.assertEqual(paper.read_text(encoding="utf-8"), candidate)

    def test_qa_loop_step_commits_safe_semi_auto_candidate_when_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_trace_path = artifact_dir / "citation_support_review.trace.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            original_trace = {"manuscript_sha256": "original-hash"}
            citation_trace_path.write_text(json.dumps(original_trace), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                citation_trace_path.write_text(json.dumps({"manuscript_sha256": "candidate-hash"}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.payload["verdict"], "ready_for_human_finalization")
            self.assertNotIn("candidate_approval", result.payload)
            self.assertEqual(result.payload["candidate_auto_commit"]["status"], "committed_for_continued_qa")
            self.assertEqual(result.payload["candidate_progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertTrue(result.payload["candidate_progress"]["forward_progress"])
            self.assertEqual(result.payload["candidate_state"]["qa_loop_plan_verdict"], "ready_for_human_finalization")
            self.assertEqual(result.payload["candidate_state"]["after"]["failing_codes"], [])
            self.assertEqual(result.payload["candidate_state"]["progress"]["resolved_codes"], ["citation_support_weak"])
            self.assertEqual(result.payload["after"]["failing_codes"], [])
            self.assertTrue(result.payload["progress"]["forward_progress"])
            self.assertEqual(result.payload["verification"]["quality_eval"]["path"], str(root / "candidate-q.json"))
            self.assertEqual(result.payload["verification"]["qa_loop_plan"]["path"], str(root / "candidate-p.json"))
            self.assertNotIn("restored_current_verification", result.payload)
            self.assertEqual(json.loads(citation_trace_path.read_text(encoding="utf-8")), {"manuscript_sha256": "candidate-hash"})
            self.assertEqual(paper.read_text(encoding="utf-8"), candidate)

    def test_qa_loop_step_rolls_back_candidate_with_new_duplicate_support_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            candidate_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_duplicate_support"],
                        "checks": {
                            "citation_quality_gate": {
                                "counts": {
                                    "duplicate_reference_count": 1,
                                    "citation_bomb_count": 0,
                                }
                            }
                        },
                    }
                },
            }
            restored_eval = before_eval
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            candidate_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_density_policy_failed", "automation": "semi_auto"}],
            }
            restored_plan = before_plan
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", candidate_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", candidate_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 20)
            self.assertEqual(result.payload["verdict"], "human_needed")
            self.assertNotIn("candidate_approval", result.payload)
            self.assertEqual(result.payload["candidate_rollback"]["auto_commit_blocked_reason"], "new_failure_codes")
            self.assertEqual(
                result.payload["candidate_handoff"]["status"],
                "human_needed_candidate_rejected_by_auto_commit_gate",
            )
            self.assertEqual(result.payload["restored_current_state"]["after"]["failing_codes"], ["citation_support_weak"])
            self.assertEqual(paper.read_text(encoding="utf-8"), original)

    def test_auto_commit_gate_rejects_metric_regression_and_structural_failure(self) -> None:
        from paperorchestra.ralph_bridge import _auto_commit_progressive_citation_candidate

        before_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_support_critic": {
                            "weakly_supported_count": 1,
                        },
                        "citation_quality_gate": {
                            "counts": {
                                "duplicate_reference_count": 1,
                            }
                        },
                    },
                }
            }
        }
        after_regression = {
            "tiers": {
                "tier_2_claim_safety": {
                    "status": "fail",
                    "checks": {
                        "citation_support_critic": {
                            "weakly_supported_count": 0,
                        },
                        "citation_quality_gate": {
                            "counts": {
                                "duplicate_reference_count": 2,
                            }
                        },
                    },
                }
            }
        }

        allowed, reason = _auto_commit_progressive_citation_candidate(
            progress={
                "forward_progress": True,
                "new_codes": [],
                "before_failing_codes": ["citation_support_weak", "citation_duplicate_support"],
            },
            validation_payload={"ok": True},
            compile_payload={"ok": True},
            require_compile=True,
            before_quality_eval=before_eval,
            after_quality_eval=after_regression,
            after_codes={"citation_duplicate_support"},
            residual_citation_failures=[],
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "active_tier2_metric_regression")

        after_structural = {
            "tiers": {
                "tier_1_structural": {"status": "fail", "failing_codes": ["compile_not_clean"]},
                "tier_2_claim_safety": {"status": "pass", "failing_codes": []},
            }
        }
        allowed, reason = _auto_commit_progressive_citation_candidate(
            progress={"forward_progress": True, "new_codes": [], "before_failing_codes": ["citation_support_weak"]},
            validation_payload={"ok": True},
            compile_payload={"ok": True},
            require_compile=True,
            before_quality_eval=before_eval,
            after_quality_eval=after_structural,
            after_codes=set(),
            residual_citation_failures=[],
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "tier1_failed")

    def test_qa_loop_step_refreshes_figure_review_for_uncommitted_citation_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            original = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nOriginal.\\end{document}\n"
            candidate = "\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCandidate.\\end{document}\n"
            paper.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            stale_figure_path, stale_figure_payload = write_figure_placement_review(root)
            self.assertEqual(stale_figure_payload["manuscript_sha256"], hashlib.sha256(original.encode("utf-8")).hexdigest())
            before_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            after_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:candidate",
                "tiers": {"tier_2_claim_safety": {"status": "pass", "failing_codes": []}},
            }
            restored_eval = {
                "session_id": "po-test",
                "mode": "claim_safe",
                "manuscript_hash": "sha256:original",
                "tiers": {"tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_weak"]}},
            }
            before_plan = {
                "verdict": "continue",
                "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}],
            }
            after_plan = {"verdict": "ready_for_human_finalization", "repair_actions": []}
            restored_plan = {"verdict": "human_needed", "repair_actions": [{"code": "citation_support_critic_failed", "automation": "semi_auto"}]}
            repair_result = {"accepted": True, "candidate_path": str(root / "candidate.tex")}
            Path(repair_result["candidate_path"]).write_text(candidate, encoding="utf-8")
            artifact_dir = artifact_path(root, "paper.full.tex").parent
            citation_review_path = artifact_dir / "citation_support_review.json"
            citation_review_path.write_text(json.dumps({"summary": {"weakly_supported": 1}}), encoding="utf-8")
            candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()

            def overwrite_citation_review(*args, **kwargs):
                citation_review_path.write_text(json.dumps({"summary": {"supported": 1}}), encoding="utf-8")
                return citation_review_path

            with patch(
                "paperorchestra.ralph_bridge.write_quality_eval",
                side_effect=[
                    (root / "before-q.json", before_eval),
                    (root / "candidate-q.json", after_eval),
                    (root / "restored-q.json", restored_eval),
                ],
            ):
                with patch(
                    "paperorchestra.ralph_bridge.write_quality_loop_plan",
                    side_effect=[
                        (root / "before-p.json", before_plan),
                        (root / "candidate-p.json", after_plan),
                        (root / "restored-p.json", restored_plan),
                    ],
                ):
                    with patch(
                        "paperorchestra.ralph_bridge._citation_summary",
                        side_effect=[{"weakly_supported": 1}, {"supported": 1}, {"weakly_supported": 1}],
                    ):
                        with patch("paperorchestra.ralph_bridge.repair_citation_claims", return_value=repair_result):
                            with patch("paperorchestra.ralph_bridge.write_citation_support_review", side_effect=overwrite_citation_review):
                                result = run_qa_loop_step(root, MockProvider(), citation_evidence_mode="heuristic")

            self.assertEqual(result.exit_code, 0)
            candidate_figure = result.payload["candidate_state"]["verification"]["figure_placement_review"]
            self.assertEqual(Path(candidate_figure["path"]).resolve(), stale_figure_path.resolve())
            self.assertEqual(candidate_figure["manuscript_sha256"], candidate_hash)
            self.assertEqual(
                result.payload["candidate_progress"]["after_failing_codes"],
                [],
            )
            self.assertEqual(paper.read_text(encoding="utf-8"), candidate)
            self.assertNotIn("restored_current_verification", result.payload)

    def test_section_review_scores_are_not_flat_when_section_shapes_differ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\n"
                "This introduction surveys prior art in detail and cites foundational work~\\cite{paper1}. "
                "It also cites the implementation baseline~\\cite{paper2} while explaining the staged pipeline."
                "\n"
                "\\section{Conclusion}\n"
                "We outperform the baseline.\n"
                "\\section{Experiments}\n"
                "Accuracy improves from 91.2 to 94.8 while latency drops by 12%.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            scores = {item["section_title"]: item["score"] for item in review["sections"]}
            self.assertGreater(len(set(scores.values())), 1)

    def test_section_review_declares_scores_advisory_and_penalizes_process_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Discussion}\n"
                "This supplied source material should not appear as manuscript process prose. "
                "The technical boundary is stated as an authorial limitation.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )

            review = build_section_review(root)

            self.assertTrue(review["score_use"]["advisory"])
            self.assertFalse(review["score_use"]["load_bearing"])
            discussion = review["sections"][0]
            self.assertIn("supplied_source", discussion["process_residue_markers"])
            self.assertLess(discussion["score"], 70)

            write_section_review(root)
            check = _section_quality_check(root, load_session(root), quality_mode="claim_safe")
            self.assertFalse(check["load_bearing"])
            self.assertIn("Tier 3 after upstream Tier 0-2 pass", check["load_bearing_context"])
            self.assertIn("section_process_residue_detected", check["failing_codes"])

    def test_section_review_penalizes_uncited_claim_like_conclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0, compile_paper=False)
            state = load_session(root)
            Path(state.artifacts.paper_full_tex).write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Conclusion}\n"
                "Our results outperform the baseline and establish a new state-of-the-art result.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            review = build_section_review(root)
            conclusion = review["sections"][0]
            self.assertEqual(conclusion["citation_count"], 0)
            self.assertTrue(conclusion["claim_like"])
            self.assertIn("Add verified citations", " ".join(conclusion["required_fixes"]))
            self.assertLess(conclusion["score"], 85)

    def test_section_and_citation_critic_cli_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(cli_main(["review-sections", "--output", str(root / "section_review.json")]), 0)
                self.assertEqual(cli_main(["review-citations", "--output", str(root / "citation_review.json")]), 0)
            finally:
                os.chdir(old_cwd)
            self.assertTrue((root / "section_review.json").exists())
            self.assertTrue((root / "citation_review.json").exists())

    def test_suggest_revisions_maps_review_items_to_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sections").mkdir()
            main = root / "main.tex"
            main.write_text("\\input{sections/04_security_analysis}\n\\input{sections/05_implementation_results}\n", encoding="utf-8")
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            (root / "sections" / "05_implementation_results.tex").write_text("\\section{Implementation and Results}", encoding="utf-8")
            review = root / "review.json"
            review.write_text(json.dumps({
                "overall_score": 58,
                "summary": {"weaknesses": ["The integrity proof needs a concrete consistency-check bound."], "top_improvements": ["Clarify evaluation scope."]},
                "questions": []
            }), encoding="utf-8")
            section_review = root / "section_review.json"
            section_review.write_text(json.dumps({"sections": [{"section_title": "Security Analysis", "required_fixes": ["Add theorem resources."]}]}), encoding="utf-8")
            citation_review = root / "citation_review.json"
            citation_review.write_text(json.dumps({"items": [{"id": "cite-001", "sentence": "Reference-X is faster \\cite{prior}.", "support_status": "weakly_supported", "risk": "medium", "suggested_fix": "Narrow the comparative claim."}]}), encoding="utf-8")
            suggestions = build_revision_suggestions(main, review, section_review_json=section_review, citation_review_json=citation_review)
            self.assertEqual(suggestions["action_count"], 4)
            self.assertEqual(suggestions["actions"][0]["target_area"], "security_analysis")
            self.assertEqual(suggestions["actions"][0]["priority"], "P0")
            self.assertEqual(suggestions["actions"][0]["action_type"], "formalize_security_argument")
            self.assertEqual(suggestions["actions"][1]["target_area"], "implementation_results")
            self.assertTrue(any(action["review_trace"]["source"].startswith("section_review") for action in suggestions["actions"]))
            self.assertTrue(any(action["review_trace"]["source"] == "citation_support_review" for action in suggestions["actions"]))
            self.assertIn("security_analysis", suggestions["actions_by_target"])
            self.assertIn("word_count", suggestions["section_diagnostics"]["security_analysis"])
            self.assertIn("suggested_patch_hunk", suggestions["actions"][0])
            self.assertIn("anchor", suggestions["actions"][0]["suggested_patch_hunk"])
            self.assertIn("@@", suggestions["actions"][0]["suggested_patch_hunk"]["hunk_template"])

    def test_critique_cli_runs_full_critic_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            source = root / "source.tex"
            source.write_text("\\input{sections/04_security_analysis}\n", encoding="utf-8")
            (root / "sections").mkdir()
            (root / "sections" / "04_security_analysis.tex").write_text("\\section{Security Analysis}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["critique", "--provider", "mock", "--source-paper", str(source), "--output-dir", str(root / "critique")])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            for key in ["review", "section_review", "citation_support_review", "revision_suggestions"]:
                self.assertTrue(Path(payload[key]).exists())
            suggestions = json.loads(Path(payload["revision_suggestions"]).read_text(encoding="utf-8"))
            self.assertGreater(suggestions["action_count"], 0)

    def test_cleanup_tmp_cli_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tmp_dir = root / ".paper-orchestra" / "tmp"
            tmp_dir.mkdir(parents=True)
            (tmp_dir / "omx-exec-cli.json").write_text("{}", encoding="utf-8")
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["cleanup-tmp"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["removed_count"], 1)
            self.assertFalse((tmp_dir / "omx-exec-cli.json").exists())
