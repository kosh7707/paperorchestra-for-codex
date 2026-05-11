from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.mcp_server import TOOL_HANDLERS
from paperorchestra.boundary import author_facing_payload_markers, normalized_claim_projection
from paperorchestra.models import InputBundle
from paperorchestra.narrative import build_planning_payloads, planning_artifact_status
from paperorchestra.pipeline import (
    ContractError,
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _sanitize_manuscript_control_prose,
    _ensure_text_safe_math_macros,
    _writer_brief_from_planning,
    _author_facing_writer_brief_block,
    plan_narrative_and_claims,
    record_current_validation_report,
    write_sections,
)
from paperorchestra.providers import MockProvider
from paperorchestra.quality_loop import write_quality_eval
from paperorchestra.session import artifact_path, create_session, load_session, save_session
from paperorchestra.validator import check_claim_map_coverage, check_narrative_section_roles, check_prompt_meta_leakage


class NarrativePlanningTests(unittest.TestCase):
    def _init_session(self, root: Path):
        files = {
            "idea.md": (
                "MethodX separates streaming-mode encryption from replaceable authentication. "
                "The proof uses a hidden-state game sequence and analysis bound. "
                "Limitations are restricted to the stated deployment-scope assumptions.\n"
            ),
            "experimental_log.md": "BenchHarness benchmark measurements compare Baseline-X with 2.54x at 16 bytes.\n",
            "template.tex": (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n"
                "\\section{Security Analysis}\n\\section{Experiments}\n\\section{Discussion}\n\\end{document}\n"
            ),
            "guidelines.md": "Target venue: DemoConf\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        state = create_session(
            root,
            InputBundle(
                idea_path=str(root / "idea.md"),
                experimental_log_path=str(root / "experimental_log.md"),
                template_path=str(root / "template.tex"),
                guidelines_path=str(root / "guidelines.md"),
                cutoff_date="2024-11-01",
            ),
        )
        outline = artifact_path(root, "outline.json")
        outline.write_text(
            json.dumps(
                {
                    "plotting_plan": [],
                    "intro_related_work_plan": {"introduction_strategy": {}, "related_work_strategy": {"overview": "", "subsections": []}},
                    "section_plan": [
                        {"section_title": "Method", "subsections": []},
                        {"section_title": "Security Analysis", "subsections": []},
                        {"section_title": "Experiments", "subsections": []},
                        {"section_title": "Discussion", "subsections": []},
                    ],
                }
            ),
            encoding="utf-8",
        )
        citation_map = artifact_path(root, "citation_map.json")
        citation_map.write_text(json.dumps({"Ref2020": {"title": "Reference", "abstract": "Background."}}), encoding="utf-8")
        refs = artifact_path(root, "references.bib")
        refs.write_text("@article{Ref2020,title={Reference},year={2020}}\n", encoding="utf-8")
        state.artifacts.outline_json = str(outline)
        state.artifacts.citation_map_json = str(citation_map)
        state.artifacts.references_bib = str(refs)
        save_session(root, state)
        return state

    def test_plan_narrative_writes_three_artifacts_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)

            paths = plan_narrative_and_claims(root, MockProvider())

            self.assertEqual(set(paths), {"narrative_plan", "claim_map", "citation_placement_plan"})
            status = planning_artifact_status(root)
            self.assertEqual(status["status"], "pass")
            claim_map = json.loads(Path(paths["claim_map"]).read_text(encoding="utf-8"))
            narrative_plan = json.loads(Path(paths["narrative_plan"]).read_text(encoding="utf-8"))
            citation_plan = json.loads(Path(paths["citation_placement_plan"]).read_text(encoding="utf-8"))
            self.assertTrue(any(claim["claim_type"] == "proof" for claim in claim_map["claims"]))
            required = [claim for claim in claim_map["claims"] if claim.get("required")]
            self.assertTrue(all(claim.get("evidence_anchors") for claim in required))
            for claim in claim_map["claims"]:
                self.assertIn("text", claim)
                self.assertIn("coverage_terms", claim)
                self.assertIn("coverage_groups", claim)
                self.assertIn("authorial_claim", claim)
                self.assertIn("scope_note", claim)
            self.assertTrue(all("must_cover" in role for role in narrative_plan["section_roles"]))
            self.assertTrue(all("beat" in beat for beat in narrative_plan["story_beats"]))
            self.assertIn("placements", citation_plan)
            brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_plan)
            rendered_brief = json.dumps(brief, ensure_ascii=False)
            self.assertFalse(author_facing_payload_markers(brief), rendered_brief)
            self.assertNotIn("human-provided", rendered_brief)
            self.assertNotIn("supplied technical evidence", rendered_brief)

    def test_write_sections_fails_without_fresh_planning_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)

            with self.assertRaisesRegex(ContractError, "paperorchestra plan-narrative"):
                write_sections(root, MockProvider())

    def test_domain_neutral_method_planning_does_not_invent_streaming_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            Path(state.inputs.idea_path).write_text(
                "The method uses a randomized scheduling construction with a run-specific schedule token for replay avoidance.\n",
                encoding="utf-8",
            )
            Path(state.inputs.experimental_log_path).write_text("No benchmark table yet.\n", encoding="utf-8")

            paths = plan_narrative_and_claims(root, MockProvider())
            claim_map = json.loads(Path(paths["claim_map"]).read_text(encoding="utf-8"))
            method_claims = [claim for claim in claim_map["claims"] if claim.get("claim_type") == "method"]

            self.assertTrue(method_claims)
            rendered = json.dumps(method_claims, ensure_ascii=False)
            self.assertNotIn("streaming-mode", rendered)
            self.assertNotIn("replaceable authentication", rendered)
            self.assertNotIn("authentication", rendered.lower())
            coverage_terms = {term for claim in method_claims for group in claim.get("coverage_groups", []) for term in group}
            self.assertIn("run-specific", coverage_terms)
            self.assertNotIn("counter", coverage_terms)
            self.assertNotIn("authentication", coverage_terms)

    def test_domain_neutral_benchmark_planning_does_not_invent_baseline_codec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            Path(state.inputs.idea_path).write_text("A scheduler paper with measured queue latency.\n", encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text(
                "Benchmark measurements report p95 latency of 12.7 ms and throughput of 4.2 jobs/s for the scheduler.\n",
                encoding="utf-8",
            )

            paths = plan_narrative_and_claims(root, MockProvider())
            claim_map = json.loads(Path(paths["claim_map"]).read_text(encoding="utf-8"))
            benchmark_claims = [claim for claim in claim_map["claims"] if claim.get("claim_type") == "benchmark"]

            self.assertTrue(benchmark_claims)
            rendered = json.dumps(benchmark_claims, ensure_ascii=False)
            self.assertNotIn("AES", rendered)
            self.assertNotIn("GCM", rendered)
            coverage_terms = {term for claim in benchmark_claims for group in claim.get("coverage_groups", []) for term in group}
            self.assertIn("benchmark", coverage_terms)
            self.assertIn("measurement", coverage_terms)
            self.assertNotIn("AES", coverage_terms)
            self.assertNotIn("GCM", coverage_terms)

    def test_benchmark_claim_coverage_ignores_generated_source_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            Path(state.inputs.idea_path).write_text("A benchmark paper about measured queue latency.\n", encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text(
                "% Fresh PaperOrchestra smoke input: deterministic benchmark brief.\n"
                "% Derived only from registered source material.\n"
                "Benchmark measurements report p95 latency of 12.7 ms using an implementation profile "
                "that compares message-size settings for the scheduler.\n",
                encoding="utf-8",
            )

            paths = plan_narrative_and_claims(root, MockProvider())
            claim_map = json.loads(Path(paths["claim_map"]).read_text(encoding="utf-8"))
            benchmark_claim = next(claim for claim in claim_map["claims"] if claim.get("claim_type") == "benchmark")

            rendered = json.dumps(benchmark_claim, ensure_ascii=False).lower()
            for generated_term in ("fresh", "paperorchestra", "smoke", "deterministic"):
                self.assertNotIn(generated_term, rendered)
            self.assertEqual(
                benchmark_claim["coverage_groups"][:3],
                [["benchmark", "measurement"], ["implementation", "profile"], ["message", "size"]],
            )

    def test_benchmark_planning_preserves_percentage_measurement_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            Path(state.inputs.idea_path).write_text("A benchmark paper about measured accuracy.\n", encoding="utf-8")
            Path(state.inputs.experimental_log_path).write_text(
                "% Fresh PaperOrchestra smoke input: deterministic benchmark brief.\n"
                "Benchmark measurements show accuracy improved to 81.2% on DemoSet with "
                "an implementation profile and message-size sweep from 50%–68% load.\n",
                encoding="utf-8",
            )

            paths = plan_narrative_and_claims(root, MockProvider())
            claim_map = json.loads(Path(paths["claim_map"]).read_text(encoding="utf-8"))
            benchmark_claim = next(claim for claim in claim_map["claims"] if claim.get("claim_type") == "benchmark")
            rendered = json.dumps(benchmark_claim, ensure_ascii=False)

            self.assertIn("81.2% on DemoSet", rendered)
            self.assertIn("50%–68% load", rendered)
            self.assertNotIn("Fresh PaperOrchestra", rendered)

    def test_benchmark_claim_coverage_requires_semantic_benchmark_boundaries(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-003",
                    "required": True,
                    "target_section": "Evaluation",
                    "evidence_anchors": [{"source_ref": "experimental_log.md"}],
                    "coverage_groups": [["benchmark", "measurement"], ["implementation", "profile"], ["message", "size"]],
                }
            ]
        }
        thin_latex = "\\section{Evaluation}\nThe benchmark measurements are reported conservatively.\n"
        complete_latex = (
            "\\section{Evaluation}\n"
            "The benchmark measurements are limited to the reported implementation profiles "
            "and message-size settings from the experimental log.\n"
        )

        thin_codes = [issue.code for issue in check_claim_map_coverage(thin_latex, claim_map)]
        complete_codes = [issue.code for issue in check_claim_map_coverage(complete_latex, claim_map)]

        self.assertIn("required_claim_missing", thin_codes)
        self.assertNotIn("required_claim_missing", complete_codes)
        self.assertNotIn("required_claim_keyword_stuffing", complete_codes)

    def test_mcp_plan_narrative_writes_three_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)

            result = TOOL_HANDLERS["plan_narrative"]({"cwd": str(root), "provider": "mock"})
            payload = json.loads(result["content"][0]["text"])

            self.assertTrue(Path(payload["narrative_plan"]).exists())
            self.assertTrue(Path(payload["claim_map"]).exists())
            self.assertTrue(Path(payload["citation_placement_plan"]).exists())

    def test_claim_coverage_ignores_comments_and_wrong_sections(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-001",
                    "required": True,
                    "target_section": "Method",
                    "evidence_anchors": [{"source_ref": "idea.md"}],
                    "coverage_groups": [["counter", "mode"], ["authentication"]],
                }
            ]
        }
        commented = "\\section{Method}\n% streaming mode authentication\nVisible prose only.\n"
        wrong_section = "\\section{Introduction}\nStreaming schedule authentication.\n\\section{Method}\nEmpty.\n"

        self.assertTrue(check_claim_map_coverage(commented, claim_map))
        wrong_codes = [issue.code for issue in check_claim_map_coverage(wrong_section, claim_map)]
        self.assertIn("required_claim_missing", wrong_codes)

    def test_claim_coverage_accepts_common_plural_term_variants(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-004",
                    "required": True,
                    "target_section": "Discussion and Limitations",
                    "evidence_anchors": [{"source_ref": "idea.md"}],
                    "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                }
            ]
        }
        latex = (
            "\\section{Discussion and Limitations}\n"
            "The conclusions remain within stated limitations, assumptions, and claim boundaries. "
            "This scope does not extend beyond the presented evidence.\n"
        )

        codes = [issue.code for issue in check_claim_map_coverage(latex, claim_map)]

        self.assertNotIn("required_claim_missing", codes)
        self.assertNotIn("required_claim_keyword_stuffing", codes)

    def test_narrative_must_cover_and_must_not_claim(self) -> None:
        narrative = {
            "section_roles": [
                {
                    "section_title": "Discussion",
                    "must_cover": ["deployment-scope assumptions"],
                    "must_not_claim": ["camera-ready"],
                }
            ],
            "story_beats": [{"target_section": "Discussion", "beat": "deployment-scope assumptions"}],
        }
        latex = "\\section{Discussion}\nThis is camera-ready but omits the required boundary.\n"

        codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

        self.assertIn("narrative_section_role_missing", codes)
        self.assertIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_allows_explicit_negation(self) -> None:
        narrative = {
            "section_roles": [
                {
                    "section_title": "Discussion",
                    "must_cover": [],
                    "must_not_claim": ["submission ready", "camera-ready"],
                }
            ]
        }
        latex = (
            "\\section{Discussion}\n"
            "This draft is not a submission-ready manuscript and is not camera-ready; "
            "final figures and bibliography curation remain human-owned.\n"
        )

        codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

        self.assertNotIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_allows_extended_boundary_negation(self) -> None:
        narrative = {
            "section_roles": [
                {
                    "section_title": "Discussion",
                    "must_cover": [],
                    "must_not_claim": ["human review is unnecessary"],
                }
            ]
        }
        latex = (
            "\\section{Discussion}\n"
            "The present evidence should not be interpreted as showing that "
            "human review is unnecessary. Final judgment remains human-owned.\n"
        )

        codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

        self.assertNotIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_rejects_unrelated_negation_before_violation(self) -> None:
        cases = [
            ("human review is unnecessary", "The draft is not complete, but human review is unnecessary."),
            ("submission ready", "This is not final, but it is submission ready."),
            ("camera-ready", "This is not final, but it is camera-ready."),
            ("human review is unnecessary", "The draft is never polished enough to ship, yet human review is unnecessary."),
        ]
        for forbidden, sentence in cases:
            with self.subTest(forbidden=forbidden, sentence=sentence):
                narrative = {
                    "section_roles": [
                        {
                            "section_title": "Discussion",
                            "must_cover": [],
                            "must_not_claim": [forbidden],
                        }
                    ]
                }
                latex = f"\\section{{Discussion}}\n{sentence}\n"

                codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

                self.assertIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_allows_boundary_conclusion_prose(self) -> None:
        cases = [
            ("human review is unnecessary", "No one should conclude that human review is unnecessary."),
            (
                "human review is unnecessary",
                "The evidence should not be interpreted as showing, however indirectly, that human review is unnecessary.",
            ),
            ("camera-ready", "This draft is not yet camera-ready."),
            ("submission-ready", "This draft is not yet submission-ready."),
            ("human review is unnecessary", "It is not true that human review is unnecessary."),
            ("camera-ready", "This draft is non-camera-ready."),
            ("human review is unnecessary", "No evidence shows that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not claim that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not currently claim that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not directly claim that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not claim or imply that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not claim, assert, or imply that human review is unnecessary."),
            ("human review is unnecessary", "Overall the paper does not claim that human review is unnecessary."),
            ("human review is unnecessary", "In this sentence, the paper does not claim that human review is unnecessary."),
            ("human review is unnecessary", "The current draft also does not claim that human review is unnecessary."),
            ("guaranteed scientific correctness", "It does not replace human review and does not claim guaranteed scientific correctness."),
            ("guaranteed scientific correctness", "The goal is not to claim guaranteed scientific correctness."),
            (
                "human review is unnecessary",
                "In the quoted discussion, the paper does not claim that human review is unnecessary.",
            ),
            ("human review is unnecessary", "We do not claim that human review is unnecessary."),
            (
                "human review is unnecessary",
                "The evidence should not be interpreted as evidence that human review is unnecessary.",
            ),
        ]
        for forbidden, sentence in cases:
            with self.subTest(forbidden=forbidden, sentence=sentence):
                narrative = {
                    "section_roles": [
                        {
                            "section_title": "Discussion",
                            "must_cover": [],
                            "must_not_claim": [forbidden],
                        }
                    ]
                }
                latex = f"\\section{{Discussion}}\n{sentence}\n"

                codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

                self.assertNotIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_rejects_hedged_affirmative_that_clauses(self) -> None:
        cases = [
            ("human review is unnecessary", "It is not surprising that human review is unnecessary."),
            ("camera-ready", "It is not guaranteed that this is camera-ready."),
            ("camera-ready", "It is not incorrect to call this camera-ready."),
            (
                "human review is unnecessary",
                "It would be misleading to say the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "We reject the idea that the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "It is false that the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "It is wrong to say the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "It would be inaccurate to say the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "It is misleading to think the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "We deny that the paper does not claim that human review is unnecessary.",
            ),
            ("human review is unnecessary", "The paper does not necessarily claim that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not necessarily imply that human review is unnecessary."),
            ("human review is unnecessary", "The paper does not necessarily show that human review is unnecessary."),
            (
                "human review is unnecessary",
                "The reviewer wrote: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "According to the reviewer, the paper does not claim that human review is unnecessary.",
            ),
            (
                "guaranteed scientific correctness",
                "The reviewer says it does not replace human review and does not claim guaranteed scientific correctness.",
            ),
            (
                "human review is unnecessary",
                'The reviewer wrote, "the paper does not claim that human review is unnecessary."',
            ),
            (
                "human review is unnecessary",
                'According to the reviewer, "we do not claim that human review is unnecessary."',
            ),
            ("human review is unnecessary", "Quoted: the paper does not claim that human review is unnecessary."),
            (
                "human review is unnecessary",
                "According to the editor, the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The reviewers wrote: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The editors wrote: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The comments say: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The commentary says: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The sentence reads: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The excerpt reads: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The passage says: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The note says: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The reviewer comments: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The reviewers comment: the paper does not claim that human review is unnecessary.",
            ),
            ("human review is unnecessary", '"The paper does not claim that human review is unnecessary."'),
            ("human review is unnecessary", "'The paper does not claim that human review is unnecessary.'"),
            ("human review is unnecessary", '"We do not claim that human review is unnecessary."'),
            (
                "human review is unnecessary",
                "The editor wrote: the paper does not claim that human review is unnecessary.",
            ),
            (
                "human review is unnecessary",
                "The abstract says: the paper does not claim that human review is unnecessary.",
            ),
            ("human review is unnecessary", "Per the reviewer, the paper does not claim that human review is unnecessary."),
            (
                "human review is unnecessary",
                "We quote the sentence: the paper does not claim that human review is unnecessary.",
            ),
        ]
        for forbidden, sentence in cases:
            with self.subTest(forbidden=forbidden, sentence=sentence):
                narrative = {
                    "section_roles": [
                        {
                            "section_title": "Discussion",
                            "must_cover": [],
                            "must_not_claim": [forbidden],
                        }
                    ]
                }
                latex = f"\\section{{Discussion}}\n{sentence}\n"

                codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

                self.assertIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_rejects_visible_latex_markup_claims(self) -> None:
        cases = [
            ("camera-ready", "This draft is \\emph{camera-ready}."),
            ("submission-ready", "This draft is \\textbf{submission-ready}."),
        ]
        for forbidden, sentence in cases:
            with self.subTest(forbidden=forbidden, sentence=sentence):
                narrative = {
                    "section_roles": [
                        {
                            "section_title": "Discussion",
                            "must_cover": [],
                            "must_not_claim": [forbidden],
                        }
                    ]
                }
                latex = f"\\section{{Discussion}}\n{sentence}\n"

                codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

                self.assertIn("narrative_forbidden_claim_present", codes)

    def test_narrative_must_not_claim_rejects_not_only_or_not_merely_affirmations(self) -> None:
        cases = [
            ("camera-ready", "This is not only camera-ready but also complete."),
            ("submission-ready", "This is not merely submission-ready; it is archival."),
        ]
        for forbidden, sentence in cases:
            with self.subTest(forbidden=forbidden, sentence=sentence):
                narrative = {
                    "section_roles": [
                        {
                            "section_title": "Discussion",
                            "must_cover": [],
                            "must_not_claim": [forbidden],
                        }
                    ]
                }
                latex = f"\\section{{Discussion}}\n{sentence}\n"

                codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

                self.assertIn("narrative_forbidden_claim_present", codes)

    def test_default_narrative_guard_rejects_submission_readiness_overclaim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session(root)
            plan_narrative_and_claims(root)
            narrative, _claim_map, _citation_plan = build_planning_payloads(root)

            latex = (
                "\\section{Discussion}\n"
                "This section discusses deployment-scope limitations, assumptions, and boundaries, "
                "but the draft is camera-ready and submission ready.\n"
            )
            codes = [issue.code for issue in check_narrative_section_roles(latex, narrative)]

            self.assertIn("narrative_forbidden_claim_present", codes)

    def test_claim_boundary_paragraph_is_added_to_existing_discussion(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-004",
                    "target_section": "Discussion",
                    "required": True,
                }
            ]
        }
        latex = "\\section{Discussion}\nThis section discusses scope.\n\\section{Conclusion}\nDone.\n"

        rendered = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)

        codes = [issue.code for issue in check_claim_map_coverage(rendered, {
            "claims": [
                {
                    "id": "claim-004",
                    "target_section": "Discussion",
                    "required": True,
                    "evidence_anchors": [{"source_ref": "guidelines.md"}],
                    "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                }
            ]
        })]
        self.assertIn("stated limitations, assumptions", rendered)
        self.assertIn("technical boundary and scope", rendered)
        self.assertNotIn("supplied source", rendered)
        self.assertNotIn("required_claim_missing", codes)
        self.assertNotIn("required_claim_keyword_stuffing", codes)

    def test_claim_boundary_section_uses_required_discussion_alias_title(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-004",
                    "target_section": "Discussion and Limitations",
                    "required": True,
                }
            ]
        }
        latex = "\\section{Implementation and Results}\nResults.\n\\section{Conclusion}\nDone.\n"

        rendered = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)

        self.assertIn("\\section{Discussion and Limitations}", rendered)
        self.assertIn("stated limitations, assumptions", rendered)
        self.assertLess(rendered.index("\\section{Discussion and Limitations}"), rendered.index("\\section{Conclusion}"))
        codes = [
            issue.code
            for issue in check_claim_map_coverage(
                rendered,
                {
                    "claims": [
                        {
                            "id": "claim-004",
                            "target_section": "Discussion and Limitations",
                            "required": True,
                            "evidence_anchors": [{"source_ref": "guidelines.md"}],
                            "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                        }
                    ]
                },
            )
        ]
        self.assertNotIn("required_claim_missing", codes)

    def test_manuscript_control_prose_sanitizer_rewrites_common_source_packet_phrases(self) -> None:
        latex = (
            "\\section{Security Analysis}\n"
            "The proof reduces integrity to ideas directly supported by the supplied source material. "
            "The resulting theorem from the supplied source is as follows. "
            "The draft remains bounded by the supplied source boundary and does not add an external claim.\n"
        )

        rendered = _sanitize_manuscript_control_prose(latex)
        codes = [issue.code for issue in check_claim_map_coverage(rendered, {"claims": []})]

        self.assertIn("stated evidence", rendered)
        self.assertIn("stated specification", rendered)
        self.assertIn("claims remain bounded", rendered)
        self.assertNotIn("supplied source material", rendered)
        self.assertNotIn("supplied source is", rendered)
        self.assertNotIn("supplied source boundary", rendered)
        self.assertNotIn("prompt_meta_leakage", codes)

    def test_manuscript_sanitizer_rewrites_cref_to_portable_ref(self) -> None:
        latex = "\\section{Discussion} See \\cref{thm:artifact} and \\Cref{fig:flow}."

        rendered = _sanitize_manuscript_control_prose(latex)

        self.assertIn("\\ref{thm:artifact}", rendered)
        self.assertIn("\\ref{fig:flow}", rendered)
        self.assertNotIn("\\cref", rendered)
        self.assertNotIn("\\Cref", rendered)

    def test_manuscript_sanitizer_rewrites_capitalized_reference_pseudo_macros(self) -> None:
        latex = (
            "\\section{Evaluation}\n"
            "\\Table~\\ref{tab:smoke-results} reports the registered outcomes. "
            "\\Figure\\ref{fig:flow} summarizes the workflow."
        )

        rendered = _sanitize_manuscript_control_prose(latex)

        self.assertIn("Table~\\ref{tab:smoke-results}", rendered)
        self.assertIn("Figure\\ref{fig:flow}", rendered)
        self.assertNotIn("\\Table", rendered)
        self.assertNotIn("\\Figure", rendered)

    def test_manuscript_sanitizer_rewrites_nonportable_citation_commands(self) -> None:
        latex = (
            "\\section{Related Work}\n"
            "\\citet{Alpha} frames the setting. "
            "Prior systems are adjacent~\\citep[see][p.~4]{Beta,Gamma}. "
            "\\textcite{Delta} discusses provenance. "
            "Whitespace forms include \\citet {Zeta} and \\textcite\n{Eta}. "
            "Portable forms \\cite{Epsilon} and \\cite [see]{Theta} remain portable; "
            "\\nocite{Hidden} is not a citation claim."
        )

        rendered = _sanitize_manuscript_control_prose(latex)

        self.assertIn("\\cite{Alpha}", rendered)
        self.assertIn("\\cite{Beta,Gamma}", rendered)
        self.assertIn("\\cite{Delta}", rendered)
        self.assertIn("\\cite{Epsilon}", rendered)
        self.assertIn("\\cite{Zeta}", rendered)
        self.assertIn("\\cite{Eta}", rendered)
        self.assertIn("\\cite [see]{Theta}", rendered)
        self.assertIn("\\nocite{Hidden}", rendered)
        self.assertNotIn("\\citet", rendered)
        self.assertNotIn("\\citep", rendered)
        self.assertNotIn("\\textcite", rendered)

    def test_manuscript_control_prose_sanitizer_rewrites_plural_supplied_materials(self) -> None:
        variants = [
            "supplied materials",
            "provided materials",
            "supplied technical materials",
            "provided technical materials",
            "supplied log",
            "provided log",
            "available log",
            "supplied file",
            "provided analysis",
            "supplied analyses",
            "provided analyses",
            "available file",
            "supplied evidence",
            "provided theorem statement",
            "supplied packet",
            "supplied proof source",
            "supplied benchmark log",
            "supplied benchmark logs",
            "method packet",
            "Following the packet",
            "As specified in the packet",
            "manuscript plan",
        ]

        for phrase in variants:
            with self.subTest(phrase=phrase):
                latex = f"\\section{{Discussion and Limitations}}\nThe conclusion is bounded by the {phrase}.\n"
                self.assertTrue(check_prompt_meta_leakage(latex), phrase)

                rendered = _sanitize_manuscript_control_prose(latex)

                self.assertTrue(
                    "stated evidence" in rendered
                    or "measurement log" in rendered
                    or "theorem statements" in rendered
                    or "paper outline" in rendered,
                    rendered,
                )
                self.assertNotIn(phrase, rendered.lower())
                self.assertNotIn("supplied", rendered.lower())
                self.assertNotIn("provided", rendered.lower())
                self.assertNotIn("available log", rendered.lower())
                self.assertFalse(check_prompt_meta_leakage(rendered), rendered)

    def test_manuscript_control_prose_sanitizer_removes_internal_template_comment(self) -> None:
        latex = (
            "\\begin{abstract}\n"
            "% PaperOrchestra writes this.\n"
            "\\end{abstract}\n"
            "\\section{Introduction}\n"
            "% PaperOrchestra:auto-repaired figure:fig_framework_overview\n"
            "The paper studies a bounded deployment-scope setting.\n"
        )

        rendered = _sanitize_manuscript_control_prose(latex)

        self.assertNotIn("PaperOrchestra writes this", rendered)
        self.assertIn("PaperOrchestra:auto-repaired figure:fig_framework_overview", rendered)
        self.assertFalse(check_prompt_meta_leakage(rendered), rendered)

    def test_manuscript_control_prose_sanitizer_replays_20260502_failed_smoke_excerpt(self) -> None:
        latex = (
            "\\section{Background}\n"
            "The evaluated baselines are precisely the protected-channel algorithms standardized for the TLS~1.3 "
            "setting studied in the benchmark packet: Baseline-128-X, Baseline-256-X, AES-128-CCM, "
            "and ChaCha20-Poly1305.\n"
            "\\section{Conclusion}\n"
            "Three extensions are directly suggested by the supplied materials. The first is a "
            "stronger concrete analysis of the authentication component.\n"
        )
        self.assertTrue(check_prompt_meta_leakage(latex))

        rendered = _sanitize_manuscript_control_prose(latex)

        self.assertFalse(check_prompt_meta_leakage(rendered), rendered)
        self.assertIn("benchmark evidence", rendered)
        self.assertIn("stated evidence", rendered)

    def test_manuscript_control_prose_sanitizer_rewrites_supplied_packet_artifacts_without_overreach(self) -> None:
        packet_phrases = [
            "supplied proof packet",
            "provided proof packet",
            "supplied benchmark packet",
            "provided empirical packet",
            "supplied review packet",
            "provided source packet",
            "supplied material packet",
            "provided material packet",
        ]
        for phrase in packet_phrases:
            with self.subTest(phrase=phrase):
                latex = f"\\section{{Proof}}\nThe theorem is copied from the {phrase}.\n"
                self.assertTrue(check_prompt_meta_leakage(latex), phrase)
                rendered = _sanitize_manuscript_control_prose(latex)
                self.assertFalse(check_prompt_meta_leakage(rendered), rendered)
                self.assertNotIn("packet", rendered.lower())
                self.assertNotIn("supplied", rendered.lower())
                self.assertNotIn("provided", rendered.lower())

        benign = (
            "\\section{Method}\n"
            "The packet-local theorem uses material assumptions from the deployment-scope model.\n"
        )
        self.assertEqual(_sanitize_manuscript_control_prose(benign), benign)
        self.assertFalse(check_prompt_meta_leakage(benign), benign)

    def test_claim_boundary_paragraph_is_added_when_existing_discussion_has_scattered_boundary_terms(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-004",
                    "target_section": "Discussion and Limitations",
                    "required": True,
                }
            ]
        }
        latex = (
            "\\section{Discussion and Limitations}\n"
            "The paper mentions stated assumptions in one place. "
            + ("Filler prose. " * 80)
            + "It later mentions a claim boundary, but not as a compact limitation statement.\n"
            "\\section{Conclusion}\nDone.\n"
        )

        rendered = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)

        self.assertIn("stated limitations, assumptions, and technical boundary and scope", rendered)
        codes = [
            issue.code
            for issue in check_claim_map_coverage(
                rendered,
                {
                    "claims": [
                        {
                            "id": "claim-004",
                            "target_section": "Discussion and Limitations",
                            "required": True,
                            "evidence_anchors": [{"source_ref": "guidelines.md"}],
                            "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                        }
                    ]
                },
            )
        ]
        self.assertNotIn("required_claim_keyword_stuffing", codes)
        self.assertNotIn("required_claim_missing", codes)

    def test_required_claim_scope_notes_cover_existing_target_sections(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-002",
                    "text": "The security analysis is grounded in the stated theorem, game sequence, and analysis-bound assumptions.",
                    "target_section": "Security Analysis",
                    "required": True,
                    "evidence_anchors": [{"source_ref": "security.tex"}],
                    "coverage_groups": [["security"], ["proof", "game"], ["advantage", "bound"]],
                }
            ]
        }
        latex = "\\section{Security Analysis}\nThis section states the construction context.\n"

        rendered = _ensure_required_claim_scope_notes(latex, claim_map)
        codes = [issue.code for issue in check_claim_map_coverage(rendered, claim_map)]

        self.assertIn("The security analysis is grounded in the stated theorem, game sequence, and analysis-bound assumptions", rendered)
        self.assertIn("Stronger analytical claims require a separate argument beyond the stated assumptions and proof obligations", rendered)
        self.assertNotIn("supplied source boundary", rendered)
        self.assertNotIn("provided material", rendered)
        self.assertNotIn("Source-grounded scope note", rendered)
        self.assertNotIn("required_claim_missing", codes)
        self.assertNotIn("required_claim_keyword_stuffing", codes)

    def test_writer_brief_strips_machine_planning_metadata(self) -> None:
        brief = _writer_brief_from_planning(
            {
                "thesis": "Use verified references for positioning.",
                "contribution_boundary": ["Do not invent core claims."],
                "section_roles": [
                    {
                        "section_title": "Security Analysis",
                        "role": "Explain the proof.",
                        "must_cover": ["Game sequence"],
                        "must_not_claim": ["misuse resistance"],
                    }
                ],
            },
            {
                "claims": [
                    {
                        "id": "claim-002",
                        "target_section": "Security Analysis",
                        "text": "The theorem depends on the stated game sequence.",
                        "claim_type": "security",
                        "grounding": "source_material",
                        "source_sha256": "sha256:secret",
                        "evidence_anchors": [{"source_ref": "proof.tex"}],
                        "excerpt": "Game 0 is real.",
                        "coverage_groups": [["game"]],
                    }
                ]
            },
            {"placements": [{"claim_id": "claim-002", "target_section": "Security Analysis", "citation_keys": ["Rogaway2002"]}]},
        )
        rendered = json.dumps(brief, ensure_ascii=False)

        self.assertIn("The theorem depends on the stated game sequence.", rendered)
        self.assertIn("Rogaway2002", rendered)
        self.assertNotIn("claim-002", rendered)
        self.assertNotIn("source_material", rendered)
        self.assertNotIn("source_sha256", rendered)
        self.assertNotIn("proof.tex", rendered)


    def test_normalized_projection_separates_machine_obligation_from_authorial_fields(self) -> None:
        projection = normalized_claim_projection(
            {
                "id": "claim-009",
                "text": "The draft must preserve source-grounded limitations without broadening them.",
                "machine_obligation": "The draft must preserve source-grounded limitations without broadening them.",
                "claim_type": "limitation",
                "grounding": "human_boundary",
                "target_section": "Discussion",
                "coverage_groups": [["limitation", "assumption"], ["boundary"]],
            }
        )

        self.assertEqual(projection["machine_obligation"], "The draft must preserve source-grounded limitations without broadening them.")
        self.assertNotIn("The draft must preserve", projection["authorial_claim"])
        self.assertNotIn("source-grounded", projection["scope_note"])
        self.assertEqual(projection["coverage_groups"], [["limitation", "assumption"], ["boundary"]])

    def test_generic_projection_is_domain_neutral(self) -> None:
        projection = normalized_claim_projection(
            {
                "id": "claim-method",
                "text": "The draft must preserve method constraints without broadening them.",
                "claim_type": "method",
                "target_section": "Method",
                "coverage_groups": [["method"], ["assumption"]],
            }
        )

        self.assertIn("method description", projection["authorial_claim"])
        self.assertNotIn("streaming-mode", projection["authorial_claim"])
        self.assertNotIn("authentication", projection["authorial_claim"])

    def test_writer_brief_purity_gate_rewrites_control_claims(self) -> None:
        brief = _writer_brief_from_planning(
            {
                "thesis": "Build a draft around human-provided material.",
                "contribution_boundary": ["Keep claims within the supplied technical evidence."],
                "section_roles": [
                    {
                        "section_title": "Discussion",
                        "role": "Explain scope.",
                        "must_cover": ["The draft must preserve source-grounded limitations without broadening them."],
                        "must_not_claim": [],
                    }
                ],
            },
            {
                "claims": [
                    {
                        "id": "claim-009",
                        "target_section": "Discussion",
                        "text": "The draft must preserve source-grounded limitations without broadening them.",
                        "claim_type": "limitation",
                        "grounding": "human_boundary",
                        "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                    }
                ]
            },
            {"placements": []},
        )
        rendered = json.dumps(brief, ensure_ascii=False)

        self.assertFalse(author_facing_payload_markers(brief), rendered)
        self.assertNotIn("The draft must preserve", rendered)
        self.assertNotIn("source-grounded", rendered)
        self.assertIn("technical boundary and scope", rendered)
        self.assertNotIn("human-provided", rendered)
        self.assertNotIn("supplied technical evidence", rendered)

    def test_scope_note_insertion_uses_safe_projection_not_control_text(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-009",
                    "target_section": "Discussion",
                    "text": "The draft must preserve source-grounded limitations, assumptions, and claim boundaries without broadening them.",
                    "claim_type": "limitation",
                    "grounding": "human_boundary",
                    "required": True,
                    "evidence_anchors": [{"source_ref": "idea.md"}],
                    "coverage_groups": [["limitation", "assumption"], ["boundary"]],
                }
            ]
        }
        latex = "\\section{Discussion}\nThis section states the scope.\n"

        rendered = _ensure_required_claim_scope_notes(latex, claim_map)
        codes = [issue.code for issue in check_claim_map_coverage(rendered, claim_map)]

        self.assertNotIn("The draft must preserve", rendered)
        self.assertNotIn("source-grounded", rendered)
        self.assertIn("stated limitations, assumptions, and technical boundary and scope", rendered)
        self.assertNotIn("required_claim_missing", codes)

    def test_discussion_section_uses_scope_note_projection(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-012",
                    "target_section": "Discussion",
                    "text": "The draft must preserve source-grounded limitations.",
                    "authorial_claim": "The proof applies only under the stated run-token assumptions.",
                    "scope_note": "The result is limited to the stated run-token assumptions and does not cover broader deployment settings.",
                    "claim_type": "limitation",
                    "grounding": "human_boundary",
                    "required": True,
                    "coverage_groups": [["run-token"], ["limitation"]],
                }
            ]
        }
        latex = "\\section{Conclusion}\nThis closes the paper.\n"

        rendered = _ensure_discussion_section_for_claim_boundaries(latex, claim_map)

        self.assertIn("\\section{Discussion}", rendered)
        self.assertIn("limited to the stated run-token assumptions", rendered)
        self.assertNotIn("standardization, deployment readiness", rendered)
        self.assertNotIn("submission-readiness", rendered)
        self.assertNotIn("ready_for_human_finalization", rendered)
        self.assertNotIn("The draft must preserve", rendered)
        self.assertFalse(author_facing_payload_markers({"discussion": rendered}), rendered)

    def test_discussion_fallback_uses_scholarly_scope_not_workflow_readiness_prose(self) -> None:
        claim_map = {
            "claims": [
                {
                    "id": "claim-013",
                    "target_section": "Discussion",
                    "text": "The analysis remains scoped to its evidence.",
                    "claim_type": "limitation",
                    "grounding": "human_boundary",
                    "required": True,
                    "coverage_groups": [["evidence"], ["scope"]],
                }
            ]
        }
        with patch("paperorchestra.manuscript_repair._required_claim_scope_note", return_value=""):
            rendered = _ensure_discussion_section_for_claim_boundaries("\\section{Conclusion}\nDone.\n", claim_map)

        self.assertIn("stated technical model", rendered)
        self.assertIn("presented assumptions, measurements, or evidence", rendered)
        self.assertNotIn("submission-readiness", rendered)
        self.assertNotIn("deployment-readiness", rendered)
        self.assertNotIn("ready_for_human_finalization", rendered)
        self.assertFalse(author_facing_payload_markers({"discussion": rendered}), rendered)

    def test_full_boundary_chain_keeps_control_text_out_of_brief_and_manuscript(self) -> None:
        claim = {
            "id": "claim-010",
            "target_section": "Experiments",
            "text": "The benchmark narrative must report only measurements and comparisons grounded in the experimental log.",
            "claim_type": "benchmark",
            "grounding": "experimental_log",
            "required": True,
            "evidence_anchors": [{"source_ref": "log.md"}],
            "coverage_groups": [["benchmark"], ["measurement"], ["AES", "GCM"]],
        }
        narrative_plan = {
            "thesis": "Benchmark evidence is scoped.",
            "contribution_boundary": ["Keep claims within technical evidence."],
            "section_roles": [{"section_title": "Experiments", "role": "Report measurements.", "must_cover": [claim["text"]], "must_not_claim": []}],
        }
        claim_map = {"claims": [claim]}
        brief = _writer_brief_from_planning(narrative_plan, claim_map, {"placements": []})
        latex = "\\section{Experiments}\nThis section summarizes the evaluation.\n"
        rendered = _ensure_required_claim_scope_notes(latex, claim_map)
        projection = normalized_claim_projection(claim)
        issues = check_claim_map_coverage(rendered, claim_map) + check_narrative_section_roles(
            rendered,
            {
                "section_roles": [
                    {
                        "section_title": "Experiments",
                        "coverage_requirements": [projection],
                        "must_not_claim": [],
                    }
                ],
                "story_beats": [{**projection, "beat": projection["authorial_claim"]}],
            },
        )
        combined = json.dumps(brief, ensure_ascii=False) + "\n" + rendered

        self.assertNotIn("benchmark narrative must report", combined.lower())
        self.assertFalse(author_facing_payload_markers(brief), combined)
        self.assertFalse([issue for issue in issues if issue.code in {"required_claim_missing", "narrative_section_role_missing", "narrative_story_beat_missing"}])

    def test_writer_brief_projects_evidence_anchors_as_safe_supporting_evidence(self) -> None:
        claim = {
            "id": "claim-011",
            "target_section": "Method",
            "text": "The method uses streaming-mode encryption with replaceable authentication.",
            "claim_type": "method",
            "grounding": "source_material",
            "required": True,
            "evidence_anchors": [
                {
                    "source_ref": "/tmp/private/materials/method.tex",
                    "source_sha256": "sha256:secret",
                    "evidence_excerpt": "Streaming-mode execution is composed with an independently replaceable authenticator.",
                    "line_start": 12,
                    "line_end": 14,
                }
            ],
            "coverage_groups": [["streaming-mode"], ["authentication"]],
        }
        brief = _writer_brief_from_planning(
            {"thesis": "Method evidence is scoped.", "contribution_boundary": [], "section_roles": [{"section_title": "Method", "role": "Describe the construction.", "must_cover": [], "must_not_claim": []}]},
            {"claims": [claim]},
            {"placements": []},
        )

        required_claim = brief["section_roles"][0]["required_claims"][0]
        evidence = required_claim["supporting_evidence"][0]
        rendered = json.dumps(brief, ensure_ascii=False)
        self.assertIn("replaceable authenticator", evidence["excerpt"])
        self.assertEqual(evidence["location"], "lines 12-14")
        self.assertNotIn("source_label", evidence)
        self.assertNotIn("method.tex", rendered)
        self.assertNotIn("sha256:secret", rendered)
        self.assertNotIn("/tmp/private", rendered)
        self.assertNotIn("claim-011", rendered)
        self.assertFalse(author_facing_payload_markers(brief), rendered)

    def test_all_writer_brief_prompt_paths_use_shared_purity_block(self) -> None:
        import paperorchestra.pipeline as pipeline

        for func in (pipeline.write_intro_related, pipeline.write_sections, pipeline.refine_current_paper):
            self.assertIn("_author_facing_writer_brief_block", inspect.getsource(func))

        block = _author_facing_writer_brief_block({"section_roles": [{"must_cover": ["Evidence remains scoped."]}]})
        self.assertIn('name="scholarly_authoring_brief"', block)
        self.assertNotIn("author_facing_writer_brief.json", block)

        with self.assertRaises(ContractError):
            _author_facing_writer_brief_block({"section_roles": [{"must_cover": ["claim_map.json"]}]})

    def test_text_safe_math_macros_wrap_bare_mathsf_definitions(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\newcommand{\\METHODX}{\\mathsf{MethodX}}\n"
            "\\newcommand{\\Enc}{\\mathsf{Enc}}\n"
            "\\begin{document}\n"
            "\\METHODX{} uses \\Enc{} in prose.\n"
            "\\end{document}\n"
        )

        rendered = _ensure_text_safe_math_macros(latex)

        self.assertIn("\\newcommand{\\METHODX}{\\ensuremath{\\mathsf{MethodX}}}", rendered)
        self.assertIn("\\newcommand{\\Enc}{\\ensuremath{\\mathsf{Enc}}}", rendered)

    def test_current_validation_ignores_human_final_artwork_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\section{Introduction}\n"
                "Background \\cite{Ref2020}.\n"
                "\\section{Related Work}\n"
                "Prior work \\cite{Ref2020}.\n"
                "\\section{Method}\n"
                "Method body \\cite{Ref2020}.\n"
                "\\section{Security Analysis}\n"
                "Proof body.\n"
                "\\section{Experiments}\n"
                "Benchmark body.\n"
                "\\section{Discussion}\n"
                "Limitations body.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            plot_manifest = artifact_path(root, "plot_manifest.json")
            plot_manifest.write_text(
                json.dumps(
                    {
                        "figures": [
                            {
                                "figure_id": "fig_human_final",
                                "title": "Human final artwork",
                                "caption": "Human final artwork caption",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            plot_assets = artifact_path(root, "plot-assets.json")
            plot_assets.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "figure_id": "fig_human_final",
                                "asset_kind": "generated_placeholder",
                                "review_status": "human_final_artwork_required",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.plot_manifest_json = str(plot_manifest)
            state.artifacts.plot_assets_json = str(plot_assets)
            save_session(root, state)

            _, report = record_current_validation_report(root)

            self.assertNotIn("plot_plan_not_reflected", [issue["code"] for issue in report["issues"]])

    def test_missing_planning_artifacts_route_to_tier0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Method}\nBody.\\end{document}\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)

            _, quality = write_quality_eval(root, quality_mode="claim_safe")

            tier0 = quality["tiers"]["tier_0_preconditions"]
            self.assertEqual(tier0["status"], "fail")
            self.assertIn("narrative_plan_missing", tier0["failing_codes"])
            self.assertEqual(quality["tiers"]["tier_2_claim_safety"]["status"], "skipped_due_to_upstream_fail")


if __name__ == "__main__":
    unittest.main()
