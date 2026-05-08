from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.boundary import control_prose_markers, sanitize_author_facing_text
from paperorchestra.critics import build_citation_support_review, write_citation_support_review
from paperorchestra.fresh_smoke import (
    actionable_candidate_approval_role,
    build_fresh_smoke_artifact_manifest,
    candidate_approval_issues_for_role,
    normalize_operator_feedback_draft,
    validate_evidence_completeness,
    validate_fresh_smoke_verdict,
    validate_material_invariance,
)
from paperorchestra.jobs import JobState, get_job_status, save_job
from paperorchestra.models import InputBundle
from paperorchestra.operator_feedback import (
    _stage_candidate_text_for_verification,
    apply_operator_feedback,
    build_operator_review_packet,
    derive_operator_issue_id,
    import_operator_feedback,
)
from paperorchestra.providers import BaseProvider, CompletionRequest, MockProvider
from paperorchestra.pipeline import ContractError, compile_current_paper
from paperorchestra.quality_loop_citation_support import _citation_support_check
from paperorchestra.quality_loop import append_quality_loop_history, write_quality_eval, write_quality_loop_plan
from paperorchestra.quality_loop_history import (
    operator_feedback_cycle_count,
    validate_fresh_smoke_lane_a_acceptance,
    validate_smoke_bundle_operator_feedback_cycles,
)
from paperorchestra.quality_loop_source_checks import _high_risk_claim_sweep
from paperorchestra.session import artifact_path, create_session, load_session, save_session
from paperorchestra.validator import check_prompt_meta_leakage


class StrictQualityGateHardeningTests(unittest.TestCase):
    def test_actionable_candidate_approval_ignores_already_promoted_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_path = root / "operator_feedback.execution.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "candidate_result": {
                            "candidate_approval": {
                                "status": "human_needed_candidate_ready",
                                "candidate_sha256": "sha256:abc123",
                            },
                            "candidate_progress": {"forward_progress": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "manuscript_sha256": "abc123",
                "artifacts": [{"role": "operator_feedback_execution", "path": str(execution_path)}],
            }

            self.assertIsNone(actionable_candidate_approval_role(packet))

    def test_actionable_candidate_approval_detects_unpromoted_nested_operator_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_path = root / "operator_feedback.execution.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "candidate_result": {
                            "candidate_approval": {
                                "status": "human_needed_candidate_ready",
                                "candidate_sha256": "sha256:candidate456",
                            },
                            "candidate_progress": {"forward_progress": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "manuscript_sha256": "base123",
                "artifacts": [{"role": "operator_feedback_execution", "path": str(execution_path)}],
            }

            self.assertEqual(actionable_candidate_approval_role(packet), "operator_feedback_execution")

    def test_actionable_candidate_approval_detects_unpromoted_qa_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_path = root / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "candidate_sha256": "sha256:candidate456",
                        },
                        "candidate_progress": {"forward_progress": True},
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "manuscript_sha256": "sha256:base123",
                "artifacts": [{"role": "qa_loop_execution", "path": str(execution_path)}],
            }

            self.assertEqual(actionable_candidate_approval_role(packet), "qa_loop_execution")

    def test_actionable_candidate_approval_falls_back_to_qa_when_operator_candidate_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            operator_path = root / "operator_feedback.execution.json"
            operator_path.write_text(
                json.dumps(
                    {
                        "candidate_result": {
                            "candidate_approval": {
                                "status": "human_needed_candidate_ready",
                                "candidate_sha256": "sha256:current123",
                            },
                            "candidate_progress": {"forward_progress": True},
                        }
                    }
                ),
                encoding="utf-8",
            )
            qa_path = root / "qa-loop-execution.iter-02.json"
            qa_path.write_text(
                json.dumps(
                    {
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "candidate_sha256": "sha256:new456",
                        },
                        "candidate_progress": {"forward_progress": True},
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "manuscript_sha256": "sha256:current123",
                "artifacts": [
                    {"role": "operator_feedback_execution", "path": str(operator_path)},
                    {"role": "qa_loop_execution", "path": str(qa_path)},
                ],
            }

            self.assertEqual(actionable_candidate_approval_role(packet), "qa_loop_execution")

    def test_candidate_approval_issues_for_role_strips_secondary_diagnostics(self) -> None:
        issues = [
            {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_approval",
                "rationale": "Approve the ready QA candidate.",
            },
            {
                "source_artifact_role": "operator_feedback_execution",
                "source_item_key": "attempts[0]",
                "rationale": "Stale operator branch was rolled back.",
            },
            {
                "source_artifact_role": "citation_support_review",
                "source_item_key": "cite-001",
                "rationale": "Residual citation diagnostic.",
            },
        ]

        self.assertEqual(
            candidate_approval_issues_for_role(issues, "qa_loop_execution"),
            [issues[0]],
        )

    def test_candidate_approval_issues_for_role_preserves_same_source_rationale(self) -> None:
        issues = [
            {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_approval",
                "rationale": "Approve the ready QA candidate.",
            },
            {
                "source_artifact_role": "qa_loop_execution",
                "source_item_key": "candidate_progress",
                "rationale": "The same QA execution records net progress.",
            },
            {
                "source_artifact_role": "operator_feedback_execution",
                "source_item_key": "attempts[0]",
                "rationale": "Stale operator branch was rolled back.",
            },
        ]

        self.assertEqual(
            candidate_approval_issues_for_role(issues, "qa_loop_execution"),
            issues[:2],
        )

    def test_operator_feedback_draft_downgrades_non_actionable_approval_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_path = root / "qa-loop-execution.iter-02.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "candidate_progress": {
                            "forward_progress": True,
                            "after_manuscript_hash": "sha256:candidate456",
                        },
                        "candidate_handoff": {
                            "status": "human_needed_candidate_rejected_by_citation_support",
                        },
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "packet_sha256": "packet123",
                "manuscript_sha256": "sha256:base123",
                "artifacts": [{"role": "qa_loop_execution", "path": str(execution_path)}],
            }
            draft = {
                "intent": "approve_existing_candidate",
                "issues": [
                    {
                        "source_artifact_role": "qa_loop_execution",
                        "source_item_key": "candidate_progress.forward_progress",
                        "target_section": "Whole manuscript",
                        "severity": "major",
                        "rationale": "The candidate made forward progress.",
                        "suggested_action": "Approve the existing candidate.",
                        "authority_class": "citation_support",
                        "owner_category": "author",
                    }
                ],
            }

            normalized = normalize_operator_feedback_draft(packet, draft)

            self.assertEqual(normalized["intent"], "generate_new_operator_candidate")
            self.assertEqual(len(normalized["issues"]), 1)
            self.assertEqual(normalized["issues"][0]["source_item_key"], "candidate_progress_without_candidate_approval")
            self.assertIn("no actionable candidate_approval", normalized["issues"][0]["rationale"])

    def test_operator_feedback_draft_preserves_ready_approval_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_path = root / "qa-loop-execution.iter-01.json"
            execution_path.write_text(
                json.dumps(
                    {
                        "candidate_approval": {
                            "status": "human_needed_candidate_ready",
                            "candidate_sha256": "sha256:candidate456",
                        },
                        "candidate_progress": {"forward_progress": True},
                    }
                ),
                encoding="utf-8",
            )
            packet = {
                "packet_sha256": "packet456",
                "manuscript_sha256": "sha256:base123",
                "artifacts": [{"role": "qa_loop_execution", "path": str(execution_path)}],
            }
            draft = {
                "intent": "approve_existing_candidate",
                "issues": [
                    {
                        "source_artifact_role": "qa_loop_execution",
                        "source_item_key": "candidate_approval",
                        "target_section": "Whole manuscript",
                        "severity": "major",
                        "rationale": "Ready candidate should be approved.",
                        "suggested_action": "Approve the ready candidate.",
                        "authority_class": "author_feedback",
                        "owner_category": "author",
                    },
                    {
                        "source_artifact_role": "citation_support_review",
                        "source_item_key": "cite-001",
                        "target_section": "Introduction",
                        "severity": "major",
                        "rationale": "Unrelated diagnostic.",
                        "suggested_action": "Fix unrelated claim.",
                        "authority_class": "citation_support",
                        "owner_category": "author",
                    },
                ],
            }

            normalized = normalize_operator_feedback_draft(packet, draft)

            self.assertEqual(normalized["intent"], "approve_existing_candidate")
            self.assertEqual([issue["source_artifact_role"] for issue in normalized["issues"]], ["qa_loop_execution"])

    def test_operator_feedback_fallback_issue_is_domain_neutral(self) -> None:
        packet = {"packet_sha256": "packet-neutral", "manuscript_sha256": "sha256:paper", "artifacts": []}
        normalized = normalize_operator_feedback_draft(
            packet,
            {"intent": "generate_new_operator_candidate", "issues": []},
        )

        fallback_text = json.dumps(normalized["issues"], ensure_ascii=False)
        self.assertIn("paper-specific claims", fallback_text)
        self.assertNotIn("MethodX", fallback_text)

    def test_generated_section_aliases_do_not_hard_code_project_specific_title(self) -> None:
        source = Path("paperorchestra/pipeline.py").read_text(encoding="utf-8")

        self.assertNotIn("hidden-state model and project-specific construction", source.lower())

    def test_meta_leakage_rule_name_is_domain_neutral(self) -> None:
        source = Path("paperorchestra/quality_loop_policy.py").read_text(encoding="utf-8")

        self.assertIn("figure_prompt_slug_specific", source)
        self.assertNotIn("fig_project_prompt_slug", source)

    def _write_provider_trace(self, root: Path, stem: str, command_name: str, *, mode: str = "gen", include_retry: bool = True) -> None:
        trace_dir = root / "provider-traces"
        trace_dir.mkdir(exist_ok=True)
        (trace_dir / f"{stem}.prompt.md").write_text("prompt", encoding="utf-8")
        (trace_dir / f"{stem}.response.md").write_text("response", encoding="utf-8")
        (trace_dir / f"{stem}.stderr.log").write_text("", encoding="utf-8")
        (trace_dir / f"{stem}.exitcode").write_text("0\n", encoding="utf-8")
        if include_retry:
            (trace_dir / f"{stem}.retry.jsonl").write_text('{"attempt":1,"exit_code":0}\n', encoding="utf-8")
        (trace_dir / f"{stem}.meta.json").write_text(
            json.dumps(
                {
                    "schema_version": "provider-trace-meta/1",
                    "mode": mode,
                    "command_name": command_name,
                    "prompt": f"{stem}.prompt.md",
                    "response": f"{stem}.response.md",
                    "stderr": f"{stem}.stderr.log",
                    "exitcode": f"{stem}.exitcode",
                    "retry_ledger": f"{stem}.retry.jsonl",
                }
            ),
            encoding="utf-8",
        )

    def _init_session(self, root: Path):
        files = {
            "idea.md": "## Problem Statement\nDemo construction with proof and benchmark claims.\n",
            "experimental_log.md": "# Experimental Log\nCycles: 12.5\n",
            "template.tex": "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n\\end{document}\n",
            "guidelines.md": "Target venue: DemoConf\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "figures").mkdir()
        return create_session(
            root,
            InputBundle(
                idea_path=str(root / "idea.md"),
                experimental_log_path=str(root / "experimental_log.md"),
                template_path=str(root / "template.tex"),
                guidelines_path=str(root / "guidelines.md"),
                figures_dir=str(root / "figures"),
                cutoff_date="2026-01-01",
            ),
        )

    class FakeWebProvider(BaseProvider):
        name = "fake-web"

        def complete(self, request: CompletionRequest) -> str:
            import re

            ids = sorted(set(re.findall(r'"id":\s*"(cite-\d+)"', request.user_prompt)))
            return json.dumps(
                {
                    "items": [
                        {
                            "id": item_id,
                            "support_status": "needs_manual_check",
                            "risk": "medium",
                            "claim_type": "background",
                            "evidence": [],
                            "reasoning": "Fake web provider records provenance without asserting support.",
                            "suggested_fix": "Verify manually.",
                        }
                        for item_id in ids
                    ],
                    "research_notes": ["fake web provenance path exercised"],
                }
            )

    def test_shared_process_residue_classifier_corpus(self) -> None:
        positives = [
            f"The draft refers to supplied technical material variant {idx}."
            for idx in range(10)
        ] + [
            f"Available source logs were used to write this paragraph variant {idx}."
            for idx in range(10)
        ] + [
            f"No reviewable figure files were available for this section variant {idx}."
            for idx in range(10)
        ] + [
            f"The writer brief and claim_map.json define obligations variant {idx}."
            for idx in range(10)
        ] + [
            f"The source boundary guardrail says the draft must preserve evidence variant {idx}."
            for idx in range(10)
        ]
        negatives = [
            f"The analysis is limited to the theorem assumptions and benchmark setting {idx}."
            for idx in range(10)
        ] + [
            f"Related work establishes background for protected-channel design {idx}."
            for idx in range(10)
        ] + [
            f"The paper does not include figures because the argument is algebraic {idx}."
            for idx in range(10)
        ] + [
            "Available evidence suggests the theorem bound is conservative.",
            "No figures were available in the dataset release.",
            "Available analysis in the literature supports this baseline.",
            "Let U denote the universe of available artifacts for the proof.",
        ]
        self.assertGreaterEqual(len(positives), 50)
        self.assertGreaterEqual(len(negatives), 30)
        missed = [text for text in positives if not control_prose_markers(text)]
        false_positives = [text for text in negatives if control_prose_markers(text)]
        self.assertEqual(missed, [])
        self.assertLessEqual(len(false_positives), 2)
        self.assertNotIn("Available analysis in the literature supports this baseline.", false_positives)

        q1_regressions = [
            "No figures because no reviewable figure files were available.",
            "The supplied source material bounds the draft.",
            "The benchmark narrative must report the available logs.",
            "The central theorem is supplied evidence.",
            "Following the packet, the evaluation uses these baselines.",
            "The draft follows the manuscript plan.",
        ]
        self.assertTrue(all(control_prose_markers(text) for text in q1_regressions))

    def test_validator_uses_shared_process_residue_classifier(self) -> None:
        latex = "\\section{Discussion}\nNo reviewable figure files were available in this packet."
        issues = check_prompt_meta_leakage(latex)
        self.assertTrue(any(issue.code == "prompt_meta_leakage" for issue in issues))

    def test_sanitizer_removes_operator_process_prose(self) -> None:
        samples = [
            "Use the supplied technical material and note that no reviewable figure files were available.",
            "Use the supplied materials.",
            "Use the provided materials.",
            "Use the supplied proof packet.",
            "Use the provided material packet.",
        ]
        for raw in samples:
            with self.subTest(raw=raw):
                sanitized = sanitize_author_facing_text(raw)
                self.assertFalse(control_prose_markers(sanitized), sanitized)
                self.assertIn("stated evidence", sanitized)
                self.assertNotIn("packet", sanitized.lower())
                self.assertNotIn("supplied", sanitized.lower())
                self.assertNotIn("provided", sanitized.lower())

    def test_citation_review_flags_mixed_paper_specific_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Method}\n"
                "Prior deployment-scope systems motivate the design, and our construction proves invariant-safety security "
                "with a 2.5x benchmark improvement~\\cite{TLS13}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review = build_citation_support_review(root, evidence_mode="heuristic")

        self.assertTrue(
            any("mixed_paper_specific_citation_scope" in (item.get("flags") or []) for item in review["items"]),
            review["items"],
        )

    def test_citation_review_allows_pure_background_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Background}\n"
                "Previous work provides a proof of security for the protocol~\\cite{TLS13}.\n"
                "Prior systems use a benchmark methodology~\\cite{TLS13}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review = build_citation_support_review(root, evidence_mode="heuristic")

        self.assertFalse(
            any("mixed_paper_specific_citation_scope" in (item.get("flags") or []) for item in review["items"]),
            review["items"],
        )

    def test_citation_review_flags_paper_specific_external_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Security}\n"
                "Our construction proves invariant-safety security with the stated theorem~\\cite{TLS13}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review = build_citation_support_review(root, evidence_mode="heuristic")

        self.assertTrue(
            any("paper_specific_external_citation_scope" in (item.get("flags") or []) for item in review["items"]),
            review["items"],
        )
        self.assertTrue(any(item.get("support_status") == "unsupported" for item in review["items"]), review["items"])

    def test_high_risk_claim_sweep_does_not_skip_mixed_cited_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Security}\n"
                "Prior systems motivate the design, and our construction proves invariant-safety security "
                "with a 2.5x improvement~\\cite{TLS13}.\n",
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            obligations = artifact_path(root, "source-obligations.json")
            obligations.write_text(json.dumps({"obligations": []}), encoding="utf-8")

            sweep = _high_risk_claim_sweep(state, {"status": "pass", "path": str(obligations)})

        self.assertEqual(sweep["status"], "fail")
        self.assertEqual(sweep["failing_codes"], ["high_risk_uncited_claim"])

    def test_citation_support_check_carries_review_hash_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nBackground~\\cite{TLS13}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            review = artifact_path(root, "citation_support_review.json")
            payload = {
                "schema_version": "citation-support-review/2",
                "manuscript_sha256": __import__("hashlib").sha256(paper.read_bytes()).hexdigest(),
                "citation_map_sha256": __import__("hashlib").sha256(citation_map.read_bytes()).hexdigest(),
                "review_mode": "heuristic",
                "evidence_provenance": {"claim_support_not_metadata_lookup": True},
                "claims_checked": 1,
                "summary": {"metadata_only": 1},
                "items": [{"support_status": "metadata_only", "citation_keys": ["TLS13"], "citation_entries": [{"key": "TLS13", "title": "The Transport Layer Security Protocol Version 1.3"}]}],
            }
            review.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            expected_review_sha = __import__("hashlib").sha256(review.read_bytes()).hexdigest()
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            check = _citation_support_check(root, state, quality_mode="draft")

        self.assertEqual(check["citation_review_sha256"], expected_review_sha)
        self.assertEqual(check["canonical_summary"], {"metadata_only": 1})

    def test_web_citation_support_review_persists_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nBackground statement~\\cite{TLS13}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review_path = write_citation_support_review(root, provider=self.FakeWebProvider(), evidence_mode="web")
            review = json.loads(review_path.read_text(encoding="utf-8"))
            trace = json.loads(review_path.with_name(review_path.stem + ".trace.json").read_text(encoding="utf-8"))

        self.assertEqual(review["review_mode"], "web")
        self.assertEqual(review["evidence_provenance"]["mode"], "web")
        self.assertTrue(review["evidence_provenance"]["web_search_required"])
        self.assertTrue(review["evidence_provenance"]["model_review_used"])
        self.assertNotEqual(review["evidence_provenance"]["provider_name"], "mock")
        self.assertEqual(trace["review_mode"], "web")
        self.assertTrue(trace["web_search_required"])

    def test_qa_loop_plan_carries_citation_review_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nBackground~\\cite{TLS13}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            citation_review = artifact_path(root, "citation_support_review.json")
            payload = {
                "schema_version": "citation-support-review/2",
                "manuscript_sha256": __import__("hashlib").sha256(paper.read_bytes()).hexdigest(),
                "citation_map_sha256": __import__("hashlib").sha256(citation_map.read_bytes()).hexdigest(),
                "review_mode": "heuristic",
                "evidence_provenance": {"claim_support_not_metadata_lookup": True},
                "claims_checked": 1,
                "summary": {"metadata_only": 1},
                "items": [{"support_status": "metadata_only", "citation_keys": ["TLS13"], "citation_entries": [{"key": "TLS13"}]}],
            }
            citation_review.write_text(json.dumps(payload), encoding="utf-8")
            expected = __import__("hashlib").sha256(citation_review.read_bytes()).hexdigest()
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            quality_path, quality_eval = write_quality_eval(root, quality_mode="draft")
            _, plan = write_quality_loop_plan(root, quality_mode="draft", quality_eval_input_path=quality_path)

        self.assertEqual(quality_eval["source_artifacts"]["citation_review_sha256"], expected)
        self.assertEqual(plan["reads"]["citation_support"]["sha256"], expected)
        self.assertEqual(plan["source_artifacts"]["citation_review_sha256"], expected)
        self.assertEqual(plan["reads"]["citation_support"]["identity_status"], "pass")

    def test_qa_loop_plan_marks_tampered_citation_review_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nBackground~\\cite{TLS13}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"TLS13": {"title": "The Transport Layer Security Protocol Version 1.3"}}), encoding="utf-8")
            citation_review = artifact_path(root, "citation_support_review.json")
            payload = {
                "schema_version": "citation-support-review/2",
                "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                "citation_map_sha256": hashlib.sha256(citation_map.read_bytes()).hexdigest(),
                "review_mode": "heuristic",
                "evidence_provenance": {"claim_support_not_metadata_lookup": True},
                "claims_checked": 1,
                "summary": {"metadata_only": 1},
                "items": [{"support_status": "metadata_only", "citation_keys": ["TLS13"], "citation_entries": [{"key": "TLS13"}]}],
            }
            citation_review.write_text(json.dumps(payload), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            quality_path, quality_eval = write_quality_eval(root, quality_mode="draft")
            payload["summary"] = {"unsupported": 1}
            citation_review.write_text(json.dumps(payload), encoding="utf-8")
            _, plan = write_quality_loop_plan(root, quality_mode="draft", quality_eval_input_path=quality_path)

        self.assertNotEqual(
            plan["source_artifacts"]["citation_review_current_sha256"],
            quality_eval["source_artifacts"]["citation_review_sha256"],
        )
        self.assertEqual(plan["source_artifacts"]["citation_review_identity_status"], "stale_or_divergent")
        self.assertEqual(plan["reads"]["citation_support"]["identity_status"], "stale_or_divergent")
        self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")
        self.assertIn("citation_support_review_stale", {action["code"] for action in plan["repair_actions"]})

    def test_operator_feedback_no_promotion_preserves_selected_evidence_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Intro}\nOriginal.\n", encoding="utf-8")
            review = artifact_path(root, "review.latest.json")
            review.write_text(json.dumps({"overall_score": 50.0, "axis_scores": {}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            paper_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "human_needed",
                        "quality_eval_summary": {"manuscript_hash": paper_sha},
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="The supplied source material leaked into prose.",
                suggested_action="Remove process wording.",
            )
            issue = {
                "id": issue_id,
                "source_artifact_role": "paper_full_tex",
                "source_item_key": "Intro:p1",
                "target_section": "Intro",
                "severity": "major",
                "rationale": "The supplied source material leaked into prose.",
                "suggested_action": "Remove process wording.",
                "authority_class": "prose_rewrite",
            }
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
            imported_path, _ = import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)
            with patch("paperorchestra.operator_feedback.refine_current_paper", return_value=[]):
                with patch("paperorchestra.operator_feedback.write_quality_eval", return_value=(root / "q.json", {"tiers": {}})):
                    with patch("paperorchestra.operator_feedback.write_quality_loop_plan", return_value=(root / "p.json", {"verdict": "human_needed"})):
                        with patch("paperorchestra.operator_feedback.write_citation_support_review") as citation_review:
                            apply_operator_feedback(
                                root,
                                MockProvider(),
                                imported_feedback_path=imported_path,
                            )
        self.assertEqual(citation_review.call_args.kwargs["evidence_mode"], "web")

    def test_import_operator_feedback_rejects_packet_when_current_plan_no_longer_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nNeeds review.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            paper_sha = "sha256:" + hashlib.sha256(paper.read_bytes()).hexdigest()
            plan_path = artifact_path(root, "qa-loop.plan.json")
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "human_needed",
                        "quality_eval_summary": {"manuscript_hash": paper_sha},
                    }
                ),
                encoding="utf-8",
            )
            packet_path, packet = build_operator_review_packet(root, review_scope="tex_only")
            issue_id = derive_operator_issue_id(
                packet["packet_sha256"],
                source_artifact_role="paper_full_tex",
                source_item_key="Intro:p1",
                target_section="Intro",
                rationale="Remove process wording.",
                suggested_action="Rewrite paragraph.",
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
                                "rationale": "Remove process wording.",
                                "suggested_action": "Rewrite paragraph.",
                                "authority_class": "prose_rewrite",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "failed",
                        "quality_eval_summary": {"manuscript_hash": paper_sha},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractError, "current qa-loop.plan.json verdict=human_needed"):
                import_operator_feedback(root, packet_path=packet_path, feedback_path=feedback_path)

    def test_mcp_apply_operator_feedback_default_is_web(self) -> None:
        from paperorchestra import mcp_server

        tools = {tool["name"]: tool for tool in mcp_server.TOOLS}
        schema_prop = tools["apply_operator_feedback"]["inputSchema"]["properties"]["citation_evidence_mode"]
        self.assertEqual(schema_prop["default"], "web")
        self.assertEqual(schema_prop["enum"], ["heuristic", "model", "web"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("paperorchestra.mcp_server.apply_operator_feedback", return_value=(root / "execution.json", {"verdict": "human_needed"})) as apply:
                result = mcp_server.tool_apply_operator_feedback(
                    {"cwd": str(root), "imported_feedback_path": str(root / "imported.json"), "provider": "mock"}
                )

        self.assertFalse(result["isError"])
        self.assertEqual(apply.call_args.kwargs["citation_evidence_mode"], "web")

    def test_candidate_staging_does_not_overwrite_canonical_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            canonical = artifact_path(root, "paper.full.tex")
            candidate = artifact_path(root, "paper.operator-candidate.tex")
            canonical.write_text("\\section{Intro}\nOriginal.\n", encoding="utf-8")
            candidate.write_text("\\section{Intro}\nCandidate.\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(canonical)
            save_session(root, state)

            _stage_candidate_text_for_verification(root, candidate)

            self.assertIn("Original", canonical.read_text(encoding="utf-8"))
            self.assertEqual(Path(load_session(root).artifacts.paper_full_tex), candidate.resolve())

    def test_compile_current_paper_preserves_canonical_source_hash(self) -> None:
        class FakeCompileResult:
            pdf_exists = True
            pdf_path = ""
            clean = True
            log_path = "latex-build.log"

            def __init__(self, pdf_path: Path):
                self.pdf_path = str(pdf_path)

            def to_dict(self) -> dict[str, object]:
                return {
                    "pdf_path": self.pdf_path,
                    "log_path": self.log_path,
                    "source_path": "paper.full.tex",
                    "manuscript_sha256": "fake",
                    "pdf_sha256": "fake",
                    "return_code": 0,
                    "pdf_exists": True,
                    "clean": True,
                    "warning_summary": [],
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            canonical = artifact_path(root, "paper.full.tex")
            original = "\\newcommand{\\METHODX}{\\mathsf{MethodX}}\n\\section{Intro}\n\\METHODX text.\n"
            canonical.write_text(original, encoding="utf-8")
            state.artifacts.paper_full_tex = str(canonical)
            state.current_phase = "draft_complete"
            save_session(root, state)
            before_hash = hashlib.sha256(canonical.read_bytes()).hexdigest()
            pdf = root / "paper.full.pdf"
            pdf.write_bytes(b"%PDF fake")

            with patch("paperorchestra.pipeline.compile_latex_with_report", return_value=FakeCompileResult(pdf)):
                compile_current_paper(root)

            self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), before_hash)
            self.assertEqual(canonical.read_text(encoding="utf-8"), original)

    def test_job_status_exposes_lifecycle_and_qa_readiness_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            state.current_phase = "complete"
            save_session(root, state)
            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps({"schema_version": "qa-loop-plan/2", "verdict": "human_needed"}),
                encoding="utf-8",
            )
            job = JobState(
                job_id="job-abcdef123456",
                kind="run",
                cwd=str(root),
                created_at="2026-04-28T00:00:00Z",
                updated_at="2026-04-28T00:00:00Z",
                status="succeeded",
                session_id=state.session_id,
                completed_at="2026-04-28T00:00:01Z",
                return_code=0,
            )
            save_job(root, job)

            status = get_job_status(root, job.job_id)

        self.assertEqual(status["session_progress"]["current_phase"], "complete")
        self.assertEqual(status["session_progress"]["qa_readiness"]["verdict"], "human_needed")
        self.assertFalse(status["session_progress"]["ready_for_human_finalization"])

    def test_job_status_rejects_stale_ready_plan_after_manuscript_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            state.current_phase = "complete"
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nReady.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            old_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            quality_eval_path = artifact_path(root, "quality-eval.json")
            quality_eval = {
                "schema_version": "quality-eval/1",
                "session_id": state.session_id,
                "manuscript_hash": f"sha256:{old_sha}",
                "provenance_trust": {"level": "live"},
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass"},
                    "tier_3_scholarly_quality": {"status": "pass"},
                },
            }
            quality_eval_path.write_text(json.dumps(quality_eval), encoding="utf-8")
            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "ready_for_human_finalization",
                        "repair_actions": [],
                        "reads": {"quality_eval": f"{quality_eval_path}@sha256:{hashlib.sha256(quality_eval_path.read_bytes()).hexdigest()}"},
                        "quality_eval_summary": {"manuscript_hash": f"sha256:{old_sha}"},
                    }
                ),
                encoding="utf-8",
            )
            paper.write_text("\\documentclass{article}\n\\begin{document}\nChanged.\n\\end{document}\n", encoding="utf-8")
            job = JobState(
                job_id="job-abcdef123456",
                kind="run",
                cwd=str(root),
                created_at="2026-04-28T00:00:00Z",
                updated_at="2026-04-28T00:00:00Z",
                status="succeeded",
                session_id=state.session_id,
                completed_at="2026-04-28T00:00:01Z",
                return_code=0,
            )
            save_job(root, job)

            status = get_job_status(root, job.job_id)

        readiness = status["session_progress"]["qa_readiness"]
        self.assertEqual(readiness["verdict"], "ready_for_human_finalization")
        self.assertFalse(status["session_progress"]["ready_for_human_finalization"])
        self.assertEqual(readiness["readiness_invalid_reason"], "quality_eval_manuscript_stale")

    def test_job_status_rejects_ready_plan_without_citation_identity_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            state.current_phase = "complete"
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\nReady.\n\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            manuscript_sha = hashlib.sha256(paper.read_bytes()).hexdigest()
            quality_eval_path = artifact_path(root, "quality-eval.json")
            quality_eval = {
                "schema_version": "quality-eval/1",
                "session_id": state.session_id,
                "manuscript_hash": f"sha256:{manuscript_sha}",
                "provenance_trust": {"level": "live"},
                "tiers": {
                    "tier_0_preconditions": {"status": "pass"},
                    "tier_1_structural": {"status": "pass"},
                    "tier_2_claim_safety": {"status": "pass"},
                    "tier_3_scholarly_quality": {"status": "pass"},
                },
            }
            quality_eval_path.write_text(json.dumps(quality_eval), encoding="utf-8")
            artifact_path(root, "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "schema_version": "qa-loop-plan/2",
                        "session_id": state.session_id,
                        "verdict": "ready_for_human_finalization",
                        "repair_actions": [],
                        "reads": {"quality_eval": f"{quality_eval_path}@sha256:{hashlib.sha256(quality_eval_path.read_bytes()).hexdigest()}"},
                        "quality_eval_summary": {"manuscript_hash": f"sha256:{manuscript_sha}"},
                        "source_artifacts": {},
                    }
                ),
                encoding="utf-8",
            )
            job = JobState(
                job_id="job-abcdef123456",
                kind="run",
                cwd=str(root),
                created_at="2026-04-28T00:00:00Z",
                updated_at="2026-04-28T00:00:00Z",
                status="succeeded",
                session_id=state.session_id,
                completed_at="2026-04-28T00:00:01Z",
                return_code=0,
            )
            save_job(root, job)

            status = get_job_status(root, job.job_id)

        readiness = status["session_progress"]["qa_readiness"]
        self.assertEqual(readiness["verdict"], "ready_for_human_finalization")
        self.assertFalse(status["session_progress"]["ready_for_human_finalization"])
        self.assertEqual(readiness["readiness_invalid_reason"], "citation_support_review_stale")

    def test_operator_feedback_cycle_count_comes_from_history_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            eval_payload = {"session_id": state.session_id, "mode": "claim_safe", "tiers": {}}
            append_quality_loop_history(root, eval_payload, event_type="operator_feedback_cycle", consumes_budget=False)
            append_quality_loop_history(root, eval_payload, event_type="qa_loop_plan", consumes_budget=False)
            append_quality_loop_history(
                root,
                {"session_id": "po-other-session", "mode": "claim_safe", "tiers": {}},
                event_type="operator_feedback_cycle",
                consumes_budget=False,
            )
            append_quality_loop_history(root, eval_payload, event_type="operator_feedback_cycle", consumes_budget=False)

            self.assertEqual(operator_feedback_cycle_count(root), 2)
            self.assertEqual(operator_feedback_cycle_count(root, session_id=state.session_id), 2)
            self.assertEqual(operator_feedback_cycle_count(root, session_id="po-other-session"), 1)

    def test_smoke_bundle_operator_feedback_cycles_match_command_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readable = root / "readable"
            readable.mkdir()
            (readable / "commands.md").write_text(
                "# Command exit codes\n"
                "- `operator_apply_cycle_1`: `0`\n"
                "- `operator_apply_cycle_2`: `0`\n"
                "- `quality_eval_final`: `0`\n",
                encoding="utf-8",
            )
            (readable / "verdict.json").write_text(
                json.dumps({"operator_feedback_cycles": 2, "operator_feedback_cycles_attempted": 2}),
                encoding="utf-8",
            )

            self.assertEqual(validate_smoke_bundle_operator_feedback_cycles(root)["status"], "pass")

            (readable / "verdict.json").write_text(json.dumps({"operator_feedback_cycles": 3}), encoding="utf-8")
            mismatch = validate_smoke_bundle_operator_feedback_cycles(root)
            self.assertEqual(mismatch["status"], "fail")
            self.assertEqual(mismatch["failing_codes"], ["operator_feedback_cycle_counter_mismatch"])
            self.assertEqual(mismatch["command_operator_apply_cycles"], 2)
            self.assertEqual(mismatch["summary_operator_feedback_cycles"], 3)

            (readable / "verdict.json").write_text(
                json.dumps({"operator_feedback_cycles": 2, "operator_feedback_cycles_attempted": 1}),
                encoding="utf-8",
            )
            attempted_mismatch = validate_smoke_bundle_operator_feedback_cycles(root)
            self.assertEqual(attempted_mismatch["status"], "fail")
            self.assertEqual(attempted_mismatch["summary_operator_feedback_cycles_attempted"], 1)

    def test_fresh_smoke_lane_a_acceptance_checks_progress_attempts_and_citation_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            base_eval = {
                "schema_version": "quality-eval/1",
                "manuscript_hash": "sha256:paper-a",
                "source_artifacts": {"citation_review_sha256": "sha256:citation-a"},
                "tiers": {
                    "tier_2_claim_safety": {"status": "fail", "failing_codes": ["unsupported_claim"]},
                },
                "cross_iteration": {
                    "regression": {
                        "same_manuscript_as_previous": False,
                        "forward_progress": True,
                    }
                },
            }
            same_eval = {
                **base_eval,
                "cross_iteration": {
                    "regression": {
                        "same_manuscript_as_previous": True,
                        "forward_progress": False,
                    }
                },
            }
            (artifacts / "quality-eval.iter-01.json").write_text(json.dumps(base_eval), encoding="utf-8")
            (artifacts / "quality-eval.iter-02.json").write_text(json.dumps(same_eval), encoding="utf-8")
            (artifacts / "qa-loop-execution.iter-01.json").write_text(
                json.dumps(
                    {
                        "manuscript_sha256_before": "sha256:paper-a",
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:paper-a",
                                "gate_reasons": ["no_textual_change", "executor_returned_identical_content"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            snapshot_artifacts = artifacts / "session-snapshot-final" / "artifacts"
            snapshot_artifacts.mkdir(parents=True)
            (snapshot_artifacts / "operator_feedback.execution.json").write_text(
                json.dumps(
                    {
                        "manuscript_sha256_before": "sha256:paper-b",
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:paper-b",
                                "gate_reasons": ["no_textual_change", "executor_returned_identical_content"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            passed = validate_fresh_smoke_lane_a_acceptance(root)
            self.assertEqual(passed["status"], "pass")
            self.assertEqual(passed["predicates"]["P1"]["checked"], 1)
            self.assertEqual(passed["predicates"]["P2"]["checked"], 2)
            self.assertEqual(passed["predicates"]["P3"]["checked"], 1)

            p1_bad = {**same_eval, "cross_iteration": {"regression": {"same_manuscript_as_previous": True, "forward_progress": True}}}
            (artifacts / "quality-eval.iter-02.json").write_text(json.dumps(p1_bad), encoding="utf-8")
            failed = validate_fresh_smoke_lane_a_acceptance(root)
            self.assertEqual(failed["status"], "fail")
            self.assertIn("P1", {failure["predicate"] for failure in failed["failures"]})

            (artifacts / "quality-eval.iter-02.json").write_text(
                json.dumps({**same_eval, "source_artifacts": {"citation_review_sha256": "sha256:citation-b"}}),
                encoding="utf-8",
            )
            failed = validate_fresh_smoke_lane_a_acceptance(root)
            self.assertEqual(failed["status"], "fail")
            self.assertIn("P3", {failure["predicate"] for failure in failed["failures"]})

            (artifacts / "quality-eval.iter-02.json").write_text(json.dumps(same_eval), encoding="utf-8")
            (artifacts / "qa-loop-execution.iter-01.json").write_text(
                json.dumps(
                    {
                        "manuscript_sha256_before": "sha256:paper-a",
                        "attempts": [
                            {
                                "attempt_index": 1,
                                "candidate_sha256": "sha256:paper-a",
                                "gate_reasons": ["no_textual_change"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            failed = validate_fresh_smoke_lane_a_acceptance(root)
            self.assertEqual(failed["status"], "fail")
            self.assertIn("P2", {failure["predicate"] for failure in failed["failures"]})

    def test_fresh_smoke_lane_a_acceptance_counts_cycle_specific_operator_executions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            for cycle in range(1, 4):
                (artifacts / f"operator_feedback.execution.cycle-{cycle}.json").write_text(
                    json.dumps(
                        {
                            "manuscript_sha256_before": "sha256:paper-a",
                            "promotion_status": "rolled_back",
                            "attempts": [
                                {
                                    "attempt_index": 1,
                                    "candidate_sha256": "sha256:paper-a",
                                    "gate_reasons": ["no_textual_change", "executor_returned_identical_content"],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

            passed = validate_fresh_smoke_lane_a_acceptance(root)

            self.assertEqual(passed["status"], "pass")
            self.assertEqual(passed["predicates"]["P2"]["checked"], 3)

    def test_fresh_smoke_lane_a_acceptance_counts_operator_snapshot_mirror_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            payload = {
                "manuscript_sha256_before": "sha256:paper-a",
                "attempts": [
                    {
                        "attempt_index": 1,
                        "candidate_sha256": "sha256:paper-a",
                        "gate_reasons": ["no_textual_change", "executor_returned_identical_content"],
                    }
                ],
            }
            (artifacts / "operator_feedback.execution.json").write_text(json.dumps(payload), encoding="utf-8")
            snapshot_artifacts = artifacts / "session-snapshot-final" / "artifacts"
            snapshot_artifacts.mkdir(parents=True)
            (snapshot_artifacts / "operator_feedback.execution.json").write_text(json.dumps(payload), encoding="utf-8")

            passed = validate_fresh_smoke_lane_a_acceptance(root)

            self.assertEqual(passed["status"], "pass")
            self.assertEqual(passed["predicates"]["P2"]["checked"], 1)

    def test_live_smoke_export_declares_session_id_before_json_artifact(self) -> None:
        script = Path("scripts/live-smoke-claim-safe.sh").read_text(encoding="utf-8")
        declaration = 'session_id=""'
        artifact_use = '"session_id": "${session_id}"'
        self.assertIn(declaration, script)
        self.assertIn(artifact_use, script)
        self.assertLess(script.index(declaration), script.index(artifact_use))


    def test_fresh_smoke_verdict_schema_rejects_raw_loop_states(self) -> None:
        valid = {
            "schema_version": "fresh-smoke-verdict/1",
            "smoke_verdict": "pass_loop_verified",
            "qa_loop_terminal_verdict": "human_needed",
            "qa_loop_terminal_exit_code": 20,
            "first_failing_predicate": None,
            "first_failing_artifact": None,
            "operator_feedback_cycles": 1,
            "operator_feedback_cycles_attempted": 1,
            "operator_feedback_cycles_promoted": 0,
            "operator_feedback_cycles_rolled_back": 1,
            "operator_feedback_cycles_failed": 0,
            "material_invariance_status": "pass",
            "evidence_completeness_status": "pass",
            "lane_a_status": "pass",
            "critic_verdict": "pass",
            "quality_gate_status": "fail_tier2",
            "manuscript_readiness": "not_ready",
            "orchestration_stop_reason": "operator_cycle_cap_reached",
        }
        self.assertEqual(validate_fresh_smoke_verdict(valid)["status"], "pass")
        invalid = {**valid, "smoke_verdict": "human_needed"}
        result = validate_fresh_smoke_verdict(invalid)
        self.assertEqual(result["status"], "fail")
        self.assertIn("fresh_smoke_verdict_schema_invalid", result["failing_codes"])
        masked = {**valid, "qa_loop_terminal_verdict": "failed"}
        masked_result = validate_fresh_smoke_verdict(masked)
        self.assertEqual(masked_result["status"], "fail")
        self.assertTrue(any(failure.get("reason") == "pass_loop_verified_cannot_mask_terminal_loop_failure" for failure in masked_result["failures"]))

    def test_material_invariance_checks_manifest_ledger_boundary_and_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "examples" / "fresh-smoke-materials"
            (root / ".omx" / "state").mkdir(parents=True)
            (root / ".omx" / "state" / "current-fresh-smoke-materials-root").write_text(
                "examples/fresh-smoke-materials", encoding="utf-8"
            )
            for sub in ["inputs", "materials", "policy", "review"]:
                (material / sub).mkdir(parents=True, exist_ok=True)
            (material / "materials" / "core.tex").write_text("Core material\n", encoding="utf-8")
            (material / "policy" / "material-boundary.md").write_text("Boundary\n", encoding="utf-8")
            core_sha = hashlib.sha256((material / "materials" / "core.tex").read_bytes()).hexdigest()
            boundary_sha = hashlib.sha256((material / "policy" / "material-boundary.md").read_bytes()).hexdigest()
            (material / "inputs" / "material-manifest.json").write_text(
                json.dumps({"materials": [{"path": "materials/core.tex", "sha256": f"sha256:{core_sha}", "bytes": 14}]}),
                encoding="utf-8",
            )
            (material / "review" / "all-files.sha256").write_text(
                f"{core_sha}  ./materials/core.tex\n{boundary_sha}  ./policy/material-boundary.md\n"
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ./review/all-files.sha256\n",
                encoding="utf-8",
            )
            passed = validate_material_invariance(material, repo_root=root, expected_material_root="examples/fresh-smoke-materials")
            self.assertEqual(passed["status"], "pass")
            self.assertEqual(passed["ignored_self_entries"][0]["path"], "./review/all-files.sha256")

            (material / "materials" / "core.tex").write_text("Changed material\n", encoding="utf-8")
            failed = validate_material_invariance(material, repo_root=root, expected_material_root="examples/fresh-smoke-materials")
            self.assertEqual(failed["status"], "fail")
            self.assertIn("material_manifest_entry_mismatch", failed["failing_codes"])
            self.assertIn("material_ledger_entry_mismatch", failed["failing_codes"])

    def test_evidence_completeness_checks_command_logs_schema_and_cycle_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 1\n", encoding="utf-8")
            (root / "inputs").mkdir()
            (root / "inputs" / "provenance-ledger.json").write_text('{"items": []}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc  inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            (root / "operator-feedback").mkdir()
            (root / "provider-traces").mkdir()
            packet_snapshot_dir = root / "operator-feedback" / "operator-review-packet.cycle-1.artifacts"
            packet_snapshot_dir.mkdir()
            frozen_artifact = packet_snapshot_dir / "quality_eval.frozen.json"
            frozen_artifact.write_text('{"verdict":"human_needed"}\n', encoding="utf-8")
            frozen_sha = hashlib.sha256(frozen_artifact.read_bytes()).hexdigest()
            (root / "operator-feedback" / "operator-review-packet.cycle-1.json").write_text(
                json.dumps({"packet_sha256": "abc", "artifacts": [{"role": "quality_eval", "path": str(frozen_artifact), "sha256": frozen_sha}]}),
                encoding="utf-8",
            )
            (root / "operator-feedback" / "operator-feedback-author.cycle-1.prompt.md").write_text("prompt", encoding="utf-8")
            (root / "operator-feedback" / "operator-feedback-author.cycle-1.response.md").write_text("response", encoding="utf-8")
            (root / "operator-feedback" / "operator-feedback-author.cycle-1.exitcode").write_text("0\n", encoding="utf-8")
            (root / "operator-feedback" / "operator-feedback.cycle-1.json").write_text('{"issues":[]}\n', encoding="utf-8")
            (root / "operator-feedback" / "operator-feedback-imported.cycle-1.json").write_text('{"issues":[]}\n', encoding="utf-8")
            self._write_provider_trace(root, "0001-gen", "research_prior_work")
            (root / "critic").mkdir()
            (root / "critic" / "q1-loop-critic.prompt.md").write_text("critic prompt", encoding="utf-8")
            (root / "critic" / "q1-loop-critic.response.md").write_text("critic response", encoding="utf-8")
            (root / "final-smoke-status.txt").write_text("human_needed\n", encoding="utf-8")
            (root / "final-smoke-exit-code.txt").write_text("20\n", encoding="utf-8")
            verdict = {
                "schema_version": "fresh-smoke-verdict/1",
                "smoke_verdict": "pass_loop_verified",
                "qa_loop_terminal_verdict": "human_needed",
                "qa_loop_terminal_exit_code": 20,
                "first_failing_predicate": None,
                "first_failing_artifact": None,
                "operator_feedback_cycles": 1,
                "operator_feedback_cycles_attempted": 1,
                "operator_feedback_cycles_promoted": 0,
                "operator_feedback_cycles_rolled_back": 1,
                "operator_feedback_cycles_failed": 0,
                "material_invariance_status": "pass",
                "evidence_completeness_status": "pass",
                "lane_a_status": "pass",
                "critic_verdict": "pass",
                "quality_gate_status": "fail_tier2",
                "manuscript_readiness": "not_ready",
                "orchestration_stop_reason": "operator_cycle_cap_reached",
            }
            (root / "readable" / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text(
                (
                    "# Command exit codes\n"
                    "- `operator_packet_cycle_1`: `0`\n"
                    "- `operator_import_cycle_1`: `0`\n"
                    "- `operator_apply_cycle_1`: `0`\n"
                    "- `live_verification_provenance`: `0`\n"
                    "- `quality_eval_final`: `0`\n"
                ),
                encoding="utf-8",
            )
            for name in ["operator_packet_cycle_1", "operator_import_cycle_1", "operator_apply_cycle_1", "live_verification_provenance", "quality_eval_final", "q1_loop_critic"]:
                (root / "logs" / f"{name}.command").write_text("true\n", encoding="utf-8")
                (root / "logs" / f"{name}.stdout.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.stderr.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.exitcode").write_text("0\n", encoding="utf-8")
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json", "quality-eval.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifacts" / "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "verdict": "human_needed",
                        "orchestration_terminal": {"verdict": "human_needed", "stop_reason": "operator_cycle_cap_reached"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "artifact-manifest.json").write_text(
                json.dumps({"schema_version": "fresh-smoke-artifact-manifest/1", "files": [], "missing_referenced_artifacts": []}),
                encoding="utf-8",
            )
            passed = validate_evidence_completeness(root)
            self.assertEqual(passed["status"], "pass")
            passed_from_relative_root = validate_evidence_completeness(Path(os.path.relpath(root, Path.cwd())))
            self.assertEqual(passed_from_relative_root["status"], "pass")

            (root / "artifacts" / "qa-loop.plan.json").write_text(
                json.dumps({"verdict": "continue", "orchestration_terminal": {"verdict": "human_needed"}}),
                encoding="utf-8",
            )
            inconsistent_plan = validate_evidence_completeness(root)
            self.assertEqual(inconsistent_plan["status"], "fail")
            self.assertIn("final_plan_terminal_inconsistent", inconsistent_plan["failing_codes"])

            (root / "artifacts" / "qa-loop.plan.json").write_text(
                json.dumps(
                    {
                        "verdict": "human_needed",
                        "orchestration_terminal": {"verdict": "human_needed", "stop_reason": "operator_cycle_cap_reached"},
                    }
                ),
                encoding="utf-8",
            )

            external_artifact = root.parent / "mutable-quality-eval.json"
            external_artifact.write_text('{"verdict":"human_needed"}\n', encoding="utf-8")
            external_sha = hashlib.sha256(external_artifact.read_bytes()).hexdigest()
            (root / "operator-feedback" / "operator-review-packet.cycle-1.json").write_text(
                json.dumps({"packet_sha256": "abc", "artifacts": [{"role": "quality_eval", "path": str(external_artifact), "sha256": external_sha}]}),
                encoding="utf-8",
            )
            stale_packet = validate_evidence_completeness(root)
            self.assertEqual(stale_packet["status"], "fail")
            self.assertIn("operator_packet_artifact_snapshot_invalid", stale_packet["failing_codes"])

            (root / "operator-feedback" / "operator-review-packet.cycle-1.json").write_text(
                json.dumps({"packet_sha256": "abc", "artifacts": [{"role": "quality_eval", "path": str(frozen_artifact), "sha256": frozen_sha}]}),
                encoding="utf-8",
            )
            (root / "logs" / "quality_eval_final.exitcode").write_text("1\n", encoding="utf-8")
            failed = validate_evidence_completeness(root)
            self.assertEqual(failed["status"], "fail")
            self.assertIn("command_ledger_inconsistent", failed["failing_codes"])

    def test_evidence_completeness_requires_live_verification_provenance_command_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text(
                "# Command exit codes\n- `live_verification_provenance`: `0`\n",
                encoding="utf-8",
            )
            (root / "logs" / "live_verification_provenance.stdout.log").write_text("{}\n", encoding="utf-8")
            (root / "logs" / "live_verification_provenance.stderr.log").write_text("", encoding="utf-8")
            (root / "logs" / "live_verification_provenance.exitcode").write_text("0\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_execution_error",
                        "qa_loop_terminal_verdict": None,
                        "qa_loop_terminal_exit_code": None,
                        "first_failing_predicate": "live_verification_provenance",
                        "first_failing_artifact": "logs/live_verification_provenance.stderr.log",
                        "operator_feedback_cycles": 0,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("command_log_missing", result["failing_codes"])
            self.assertTrue(
                any(
                    item.get("path") == "logs/live_verification_provenance.command"
                    for item in result["missing"]
                    if item.get("check") == "command_log"
                )
            )

    def test_evidence_completeness_rejects_terminal_file_mismatch_for_failure_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n", encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_execution_error",
                        "qa_loop_terminal_verdict": "failed",
                        "qa_loop_terminal_exit_code": 30,
                        "first_failing_predicate": "qa_loop_terminal",
                        "first_failing_artifact": "readable/verdict.json",
                        "operator_feedback_cycles": 0,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            (root / "final-smoke-status.txt").write_text("ready_for_human_finalization\n", encoding="utf-8")
            (root / "final-smoke-exit-code.txt").write_text("0\n", encoding="utf-8")
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("terminal_status_file_mismatch", result["failing_codes"])


    def test_artifact_manifest_reports_missing_absolute_bundle_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "consumer.json").write_text(
                json.dumps({"quality_eval_path": str(root / "artifacts" / "missing-quality-eval.json")}),
                encoding="utf-8",
            )
            manifest = build_fresh_smoke_artifact_manifest(root, root)
            self.assertEqual(
                manifest["missing_referenced_artifacts"],
                [
                    {
                        "referenced_by": "artifacts/consumer.json",
                        "source": str(root / "artifacts" / "missing-quality-eval.json"),
                        "reason": "not_found",
                    }
                ],
            )

    def test_artifact_manifest_does_not_suppress_dot_prefixed_evidence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "consumer.json").write_text(json.dumps({"path": "./artifacts/missing.json"}), encoding="utf-8")
            manifest = build_fresh_smoke_artifact_manifest(root, root)
            self.assertEqual(
                manifest["missing_referenced_artifacts"],
                [{"referenced_by": "artifacts/consumer.json", "source": "artifacts/missing.json", "reason": "not_found"}],
            )

    def test_artifact_manifest_ignores_material_relative_provenance_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "material-invariance.json").write_text(
                json.dumps(
                    {
                        "checked": [
                            {"path": "materials/core.tex"},
                            {"path": "./policy/material-boundary.md"},
                            {"path": "./inputs/material-manifest.json"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manifest = build_fresh_smoke_artifact_manifest(root, root)
            self.assertEqual(manifest["missing_referenced_artifacts"], [])

    def test_artifact_manifest_does_not_suppress_material_paths_from_other_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "consumer.json").write_text(
                json.dumps({"path": "./policy/should-not-be-suppressed.md"}),
                encoding="utf-8",
            )
            manifest = build_fresh_smoke_artifact_manifest(root, root)
            self.assertEqual(
                manifest["missing_referenced_artifacts"],
                [{"referenced_by": "artifacts/consumer.json", "source": "policy/should-not-be-suppressed.md", "reason": "not_found"}],
            )

    def test_evidence_completeness_requires_research_provider_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n", encoding="utf-8")
            for suffix in ["command", "stdout.log", "stderr.log", "exitcode"]:
                (root / "logs" / f"research_prior_work.{suffix}").write_text("bash provider-wrap.sh gen\n" if suffix == "command" else ("0\n" if suffix == "exitcode" else ""), encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_critic_reject",
                        "qa_loop_terminal_verdict": None,
                        "qa_loop_terminal_exit_code": None,
                        "first_failing_predicate": "critic_not_run_yet",
                        "first_failing_artifact": None,
                        "operator_feedback_cycles": 0,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("provider_prompt_response_traces_missing", result["failing_codes"])

    def test_evidence_completeness_allows_provider_commands_without_wrapper_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "provider-traces").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n- `qa_loop_step_iter_1`: `0`\n", encoding="utf-8")
            for name in ["research_prior_work", "qa_loop_step_iter_1"]:
                (root / "logs" / f"{name}.command").write_text("bash provider-wrap.sh gen\n", encoding="utf-8")
                (root / "logs" / f"{name}.stdout.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.stderr.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.exitcode").write_text("0\n", encoding="utf-8")
            self._write_provider_trace(root, "0001-gen", "research_prior_work")
            (root / "provider-traces" / "0001-gen.attempt-1.response.md").write_text("attempt response", encoding="utf-8")
            (root / "provider-traces" / "0001-gen.attempt-1.exitcode").write_text("0\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_critic_reject",
                        "qa_loop_terminal_verdict": None,
                        "qa_loop_terminal_exit_code": None,
                        "first_failing_predicate": "critic_not_run_yet",
                        "first_failing_artifact": None,
                        "operator_feedback_cycles": 0,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "pass")
            self.assertNotIn("provider_trace_command_coverage_missing", result["failing_codes"])
            binding = [entry for entry in result["checked"] if entry.get("check") == "provider_trace_command_binding"]
            self.assertEqual(len(binding), 1)
            self.assertEqual(binding[0]["provider_commands_without_wrapper_invocation"], ["qa_loop_step_iter_1"])

    def test_evidence_completeness_rejects_unbound_provider_trace_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "provider-traces").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n", encoding="utf-8")
            for suffix in ["command", "stdout.log", "stderr.log", "exitcode"]:
                (root / "logs" / f"research_prior_work.{suffix}").write_text(
                    "bash provider-wrap.sh gen\n" if suffix == "command" else ("0\n" if suffix == "exitcode" else ""),
                    encoding="utf-8",
                )
            self._write_provider_trace(root, "0001-gen", "not_a_recorded_command")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_critic_reject",
                        "qa_loop_terminal_verdict": None,
                        "qa_loop_terminal_exit_code": None,
                        "first_failing_predicate": "critic_not_run_yet",
                        "first_failing_artifact": None,
                        "operator_feedback_cycles": 0,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("provider_trace_command_coverage_missing", result["failing_codes"])

    def test_evidence_completeness_accepts_provider_trace_command_coverage_with_multi_call_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "provider-traces").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n- `qa_loop_step_iter_1`: `0`\n", encoding="utf-8")
            for name in ["research_prior_work", "qa_loop_step_iter_1"]:
                (root / "logs" / f"{name}.command").write_text("bash provider-wrap.sh gen\n", encoding="utf-8")
                (root / "logs" / f"{name}.stdout.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.stderr.log").write_text("", encoding="utf-8")
                (root / "logs" / f"{name}.exitcode").write_text("0\n", encoding="utf-8")
            for idx, command_name in [("0001", "research_prior_work"), ("0002", "qa_loop_step_iter_1")]:
                self._write_provider_trace(root, f"{idx}-gen", command_name)
            (root / "readable" / "verdict.json").write_text(json.dumps({"schema_version":"fresh-smoke-verdict/1","smoke_verdict":"fail_critic_reject","qa_loop_terminal_verdict":None,"qa_loop_terminal_exit_code":None,"first_failing_predicate":"critic_not_run_yet","first_failing_artifact":None,"operator_feedback_cycles":0,"material_invariance_status":"pass","evidence_completeness_status":"fail","lane_a_status":"pass","critic_verdict":"not_run"}), encoding="utf-8")
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "pass")
            self.assertNotIn("provider_trace_command_coverage_missing", result["failing_codes"])
            advisory = [entry for entry in result["checked"] if entry.get("check") == "provider_trace_count_advisory"]
            self.assertEqual(len(advisory), 1)
            self.assertEqual(advisory[0]["provider_command_count"], 2)
            self.assertEqual(advisory[0]["prompt_response_trace_count"], 2)


    def test_evidence_completeness_rejects_missing_or_unknown_provider_trace_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir(); (root / "logs").mkdir(); (root / "artifacts").mkdir(); (root / "inputs").mkdir(); (root / "provider-traces").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n", encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            for suffix in ["command", "stdout.log", "stderr.log", "exitcode"]:
                (root / "logs" / f"research_prior_work.{suffix}").write_text("bash provider-wrap.sh gen\n" if suffix == "command" else ("0\n" if suffix == "exitcode" else ""), encoding="utf-8")
            for name in ["0001-gen.prompt.md", "0001-gen.response.md", "0001-gen.stderr.log", "0001-gen.exitcode"]:
                (root / "provider-traces" / name).write_text("0\n" if name.endswith("exitcode") else "x", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(json.dumps({"schema_version":"fresh-smoke-verdict/1","smoke_verdict":"fail_critic_reject","qa_loop_terminal_verdict":None,"qa_loop_terminal_exit_code":None,"first_failing_predicate":"critic_not_run_yet","first_failing_artifact":None,"operator_feedback_cycles":0,"material_invariance_status":"pass","evidence_completeness_status":"fail","lane_a_status":"pass","critic_verdict":"not_run"}), encoding="utf-8")
            missing_meta = validate_evidence_completeness(root)
            self.assertEqual(missing_meta["status"], "fail")
            self.assertIn("provider_trace_metadata_missing", missing_meta["failing_codes"])
            (root / "provider-traces" / "0001-gen.meta.json").write_text('{"command_name":"unknown","mode":"gen"}\n', encoding="utf-8")
            unknown_meta = validate_evidence_completeness(root)
            self.assertEqual(unknown_meta["status"], "fail")
            self.assertIn("provider_trace_metadata_missing", unknown_meta["failing_codes"])

    def test_evidence_completeness_requires_retry_metadata_for_attempt_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "provider-traces").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 0\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n- `research_prior_work`: `0`\n", encoding="utf-8")
            for suffix in ["command", "stdout.log", "stderr.log", "exitcode"]:
                (root / "logs" / f"research_prior_work.{suffix}").write_text("bash provider-wrap.sh gen\n" if suffix == "command" else ("0\n" if suffix == "exitcode" else ""), encoding="utf-8")
            self._write_provider_trace(root, "0001-gen", "research_prior_work", include_retry=False)
            (root / "provider-traces" / "0001-gen.attempt-1.exitcode").write_text("0\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(json.dumps({"schema_version":"fresh-smoke-verdict/1","smoke_verdict":"fail_critic_reject","qa_loop_terminal_verdict":None,"qa_loop_terminal_exit_code":None,"first_failing_predicate":"critic_not_run_yet","first_failing_artifact":None,"operator_feedback_cycles":0,"material_invariance_status":"pass","evidence_completeness_status":"fail","lane_a_status":"pass","critic_verdict":"not_run"}), encoding="utf-8")
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("provider_retry_attempt_metadata_missing", result["failing_codes"])

    def test_evidence_completeness_rejects_orphan_operator_cycle_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "operator-feedback").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 1\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            (root / "artifacts" / "session-snapshot-final").mkdir()
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n", encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_loop_feedback_not_reflected",
                        "qa_loop_terminal_verdict": "human_needed",
                        "qa_loop_terminal_exit_code": 20,
                        "first_failing_predicate": "operator_feedback",
                        "first_failing_artifact": "operator-feedback/operator-feedback.cycle-1.json",
                        "operator_feedback_cycles": 1,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            (root / "final-smoke-status.txt").write_text("human_needed\n", encoding="utf-8")
            (root / "final-smoke-exit-code.txt").write_text("20\n", encoding="utf-8")
            (root / "operator-feedback" / "operator-feedback.cycle-1.json").write_text('{"issues":[]}\n', encoding="utf-8")
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("operator_cycle_command_sequence_incomplete", result["failing_codes"])

    def test_evidence_completeness_compares_operator_history_cycle_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readable").mkdir()
            (root / "logs").mkdir()
            (root / "artifacts").mkdir()
            (root / "inputs").mkdir()
            (root / "README.md").write_text("operator_feedback_cycles: 1\n", encoding="utf-8")
            (root / "inputs" / "provenance-ledger.json").write_text('{"items":[]}\n', encoding="utf-8")
            (root / "inputs.sha256").write_text("abc inputs/idea.tex\n", encoding="utf-8")
            for artifact in ["material-invariance.json", "fresh-smoke-lane-a-acceptance.json", "meta-leakage-scan.json"]:
                (root / "artifacts" / artifact).write_text('{"status":"pass"}\n', encoding="utf-8")
            (root / "artifacts" / "qa-loop-history.jsonl").write_text(
                '{"event":"operator_feedback_cycle","cycle":1}\n{"event":"operator_feedback_cycle","cycle":2}\n',
                encoding="utf-8",
            )
            (root / "artifact-manifest.json").write_text('{"missing_referenced_artifacts":[]}\n', encoding="utf-8")
            (root / "readable" / "commands.md").write_text("# Command exit codes\n", encoding="utf-8")
            (root / "readable" / "timeline.md").write_text("# Timeline\n", encoding="utf-8")
            (root / "readable" / "verdict.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fresh-smoke-verdict/1",
                        "smoke_verdict": "fail_loop_feedback_not_reflected",
                        "qa_loop_terminal_verdict": "human_needed",
                        "qa_loop_terminal_exit_code": 20,
                        "first_failing_predicate": "operator_feedback",
                        "first_failing_artifact": "operator-feedback/operator-feedback.cycle-1.json",
                        "operator_feedback_cycles": 1,
                        "material_invariance_status": "pass",
                        "evidence_completeness_status": "fail",
                        "lane_a_status": "pass",
                        "critic_verdict": "not_run",
                    }
                ),
                encoding="utf-8",
            )
            (root / "final-smoke-status.txt").write_text("human_needed\n", encoding="utf-8")
            (root / "final-smoke-exit-code.txt").write_text("20\n", encoding="utf-8")
            result = validate_evidence_completeness(root)
            self.assertEqual(result["status"], "fail")
            self.assertIn("operator_feedback_cycle_counter_mismatch", result["failing_codes"])
