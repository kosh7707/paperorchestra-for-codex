from __future__ import annotations

import html
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import _write_full_fidelity_artifacts
from paperorchestra.eval import build_generated_citation_titles, build_session_eval_summary
from paperorchestra.fidelity import _citation_surface_health, _ensure_default_citation_partition_request
from paperorchestra.literature import registry_to_bibtex
from paperorchestra.manuscript_repair import _citation_map_for_selected_sections
from paperorchestra.models import InputBundle, VerifiedPaper
from paperorchestra.narrative import _first_key, build_planning_payloads, planning_source_hashes
from paperorchestra.pipeline import (
    _citation_map_from_registry,
    _drop_unknown_citation_keys,
    _merge_verified_entry_with_prior_keys,
    _compact_citation_map_for_prompt,
    _ensure_minimum_citation_coverage,
    record_current_validation_report,
    write_intro_related,
    write_sections,
    refine_current_paper,
    review_current_paper,
)
from paperorchestra.providers import BaseProvider, CompletionRequest
from paperorchestra.ralph_bridge_repair import repair_citation_claims
from paperorchestra.session import artifact_path, create_session, load_session, save_session
from paperorchestra.citation_integrity import build_rendered_reference_audit
from paperorchestra.validator import canonicalize_citation_keys, extract_citation_keys, validate_manuscript


def _alias_citation_map() -> dict[str, dict[str, object]]:
    primary = {
        "title": "Primary Source",
        "abstract": "Primary source discusses the background.",
        "canonical_bibtex_key": "Primary",
        "alias_bibtex_keys": ["Alias", "AliasCPG2024"],
        "citation_key_role": "canonical",
    }
    alias = dict(primary)
    alias["citation_key_role"] = "alias"
    alias_cpg = dict(primary)
    alias_cpg["citation_key_role"] = "alias"
    other = {
        "title": "Other Source",
        "abstract": "Other source.",
        "canonical_bibtex_key": "Other",
        "alias_bibtex_keys": [],
        "citation_key_role": "canonical",
    }
    return {"Alias": alias, "Primary": primary, "AliasCPG2024": alias_cpg, "Other": other}


def _init_session(root: Path):
    for name, content in {
        "idea.md": "Alias-safe orchestration keeps source identities canonical.\n",
        "experimental_log.md": "No numeric result claims.\n",
        "template.tex": (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n"
            "\\end{document}\n"
        ),
        "guidelines.md": "Demo venue.\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    return create_session(
        root,
        InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            cutoff_date="2024-11-01",
        ),
    )


def _write_planning_artifacts(root: Path, state) -> None:
    outline_path = artifact_path(root, "outline.json")
    outline_path.write_text(
        json.dumps(
            {
                "plotting_plan": [],
                "intro_related_work_plan": {
                    "introduction_strategy": {},
                    "related_work_strategy": {"overview": "", "subsections": []},
                },
                "section_plan": [
                    {"section_title": "Method", "subsections": []},
                    {"section_title": "Experiments", "subsections": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    state.artifacts.outline_json = str(outline_path)
    save_session(root, state)
    source_hashes = planning_source_hashes(root)
    narrative_path = artifact_path(root, "narrative_plan.json")
    narrative_path.write_text(json.dumps({"schema_version": "narrative-plan/1", "source_hashes": source_hashes, "section_roles": [], "story_beats": []}), encoding="utf-8")
    claim_path = artifact_path(root, "claim_map.json")
    claim_path.write_text(json.dumps({"schema_version": "claim-map/1", "source_hashes": source_hashes, "claims": []}), encoding="utf-8")
    placement_path = artifact_path(root, "citation_placement_plan.json")
    placement_path.write_text(json.dumps({"schema_version": "citation-placement-plan/1", "source_hashes": source_hashes, "placements": []}), encoding="utf-8")
    state = load_session(root)
    state.artifacts.narrative_plan_json = str(narrative_path)
    state.artifacts.claim_map_json = str(claim_path)
    state.artifacts.citation_placement_plan_json = str(placement_path)
    save_session(root, state)


def _write_alias_citation_artifacts(root: Path, *, manuscript_cites: str = "Primary"):
    state = load_session(root)
    registry_path = artifact_path(root, "citation_registry.json")
    registry_path.write_text(
        json.dumps(
            [
                {
                    "paper_id": "p1",
                    "title": "Primary Source",
                    "year": 2024,
                    "publication_date": None,
                    "venue": "DemoConf",
                    "abstract": "Primary source discusses the background.",
                    "authors": ["A. Author"],
                    "citation_count": None,
                    "external_ids": {},
                    "url": "https://example.com/primary",
                    "bibtex_key": "Primary",
                    "alias_bibtex_keys": ["Alias", "AliasCPG2024"],
                    "origin": "manual_seed",
                    "matched_query": None,
                    "title_match_ratio": None,
                    "is_after_cutoff": False,
                },
                {
                    "paper_id": "p2",
                    "title": "Other Source",
                    "year": 2023,
                    "publication_date": None,
                    "venue": "DemoConf",
                    "abstract": "Other source.",
                    "authors": ["B. Author"],
                    "citation_count": None,
                    "external_ids": {},
                    "url": "https://example.com/other",
                    "bibtex_key": "Other",
                    "alias_bibtex_keys": [],
                    "origin": "manual_seed",
                    "matched_query": None,
                    "title_match_ratio": None,
                    "is_after_cutoff": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    citation_map_path = artifact_path(root, "citation_map.json")
    citation_map_path.write_text(json.dumps(_alias_citation_map()), encoding="utf-8")
    references_path = artifact_path(root, "references.bib")
    references_path.write_text(
        "@article{Primary, title={Primary Source}, author={A. Author}, year={2024}}\n"
        "@article{Other, title={Other Source}, author={B. Author}, year={2023}}\n",
        encoding="utf-8",
    )
    paper_path = artifact_path(root, "paper.full.tex")
    paper_path.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Introduction}\n"
        f"Background framing~\\cite{{{manuscript_cites}}}.\n"
        "\\section{Related Work}\nRelated text.\n"
        "\\section{Method}\nMethod text.\n"
        "\\bibliographystyle{plain}\n\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    state.artifacts.citation_registry_json = str(registry_path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.artifacts.references_bib = str(references_path)
    state.artifacts.paper_full_tex = str(paper_path)
    save_session(root, state)
    _write_planning_artifacts(root, load_session(root))
    return load_session(root)


def _data_block(text: str, name: str) -> str:
    start = f'<DATA_BLOCK name="{name}">\n'
    begin = text.index(start) + len(start)
    end = text.index("\n</DATA_BLOCK>", begin)
    return html.unescape(text[begin:end])


def _review_json(score: int = 75) -> str:
    return json.dumps(
        {
            "paper_title": "Demo",
            "citation_statistics": {
                "estimated_unique_citations": 2,
                "citation_density_assessment": "adequate",
                "breadth_across_subareas": "adequate",
                "comparison_to_baseline": "similar",
                "notes": "ok",
            },
            "overall_score": score,
            "axis_scores": {
                axis: {"score": score, "justification": "ok"}
                for axis in [
                    "coverage_and_completeness",
                    "relevance_and_focus",
                    "critical_analysis_and_synthesis",
                    "positioning_and_novelty",
                    "organization_and_writing",
                    "citation_practices_and_rigor",
                ]
            },
            "penalties": [],
            "summary": {"strengths": ["ok"], "weaknesses": [], "top_improvements": []},
            "questions": [],
        }
    )


class CitationAliasCanonicalizationTests(unittest.TestCase):
    def test_registry_to_bibtex_omits_alias_entries_but_citation_map_keeps_alias_metadata(self) -> None:
        paper = VerifiedPaper(
            paper_id="p1",
            title="Primary Source",
            year=2024,
            publication_date=None,
            venue="DemoConf",
            abstract="Background.",
            authors=["A. Author"],
            citation_count=None,
            url="https://example.com/primary",
        )
        paper.bibtex_key = "Primary"
        paper.alias_bibtex_keys = ["Alias"]

        bib = registry_to_bibtex([paper])
        citation_map = _citation_map_from_registry([paper])

        self.assertEqual(bib.count("@inproceedings"), 1)
        self.assertIn("{Primary,", bib)
        self.assertNotIn("{Alias,", bib)
        self.assertEqual(citation_map["Primary"]["canonical_bibtex_key"], "Primary")
        self.assertEqual(citation_map["Primary"]["citation_key_role"], "canonical")
        self.assertEqual(citation_map["Alias"].get("canonical_bibtex_key"), "Primary")
        self.assertEqual(citation_map["Alias"].get("citation_key_role"), "alias")
        self.assertEqual(citation_map["Primary"].get("alias_bibtex_keys"), ["Alias"])
        self.assertEqual(citation_map["Alias"].get("alias_bibtex_keys"), ["Alias"])

    def test_live_verification_merge_preserves_alias_lookup_without_alias_bibtex_entry(self) -> None:
        prior = VerifiedPaper(
            paper_id="prior",
            title="Merged Source",
            year=2022,
            publication_date=None,
            venue="DemoConf",
            abstract="Prior abstract.",
            authors=["Prior Author"],
            citation_count=None,
            url="https://example.com/prior",
        )
        prior.bibtex_key = "PriorKey"
        prior.alias_bibtex_keys = ["SeedAlias"]
        prior.origin = "manual_seed"
        live = VerifiedPaper(
            paper_id="live",
            title="Merged Source",
            year=2022,
            publication_date=None,
            venue="DemoConf",
            abstract="Live abstract.",
            authors=["Live Author"],
            citation_count=None,
            url="https://example.com/live",
        )
        live.bibtex_key = "LiveKey"
        live.origin = "live"

        merged = _merge_verified_entry_with_prior_keys(prior, live)
        citation_map = _citation_map_from_registry([merged])
        bib = registry_to_bibtex([merged])

        self.assertIn("PriorKey", citation_map)
        self.assertIn("SeedAlias", citation_map)
        self.assertIn("LiveKey", citation_map)
        self.assertEqual(citation_map["SeedAlias"].get("canonical_bibtex_key"), "PriorKey")
        self.assertEqual(citation_map["SeedAlias"].get("citation_key_role"), "alias")
        self.assertEqual(citation_map["LiveKey"].get("canonical_bibtex_key"), "PriorKey")
        self.assertEqual(citation_map["LiveKey"].get("citation_key_role"), "alias")
        self.assertIn("{PriorKey,", bib)
        self.assertNotIn("{SeedAlias,", bib)
        self.assertNotIn("{LiveKey,", bib)

    def test_canonicalize_citation_keys_rewrites_exact_case_and_fuzzy_aliases_to_primary(self) -> None:
        citation_map = _alias_citation_map()

        latex, replacements = canonicalize_citation_keys(
            "\\citep[see][§2]{Alias, alias, ACPG2024, Other}.", citation_map
        )

        # Duplicate canonical keys are not required; implementations may dedupe
        # Primary/alias equivalents as long as aliases disappear and options stay.
        self.assertTrue(latex.startswith("\\citep[see][§2]{"))
        self.assertIn("Other", extract_citation_keys(latex))
        self.assertIn("Primary", extract_citation_keys(latex))
        self.assertNotIn("Alias", extract_citation_keys(latex))
        self.assertNotIn("alias", extract_citation_keys(latex))
        self.assertNotIn("ACPG2024", extract_citation_keys(latex))
        self.assertEqual(replacements["Alias"], "Primary")
        self.assertEqual(replacements["alias"], "Primary")
        self.assertEqual(replacements["ACPG2024"], "Primary")

    def test_validate_manuscript_counts_coverage_by_unique_canonical_sources(self) -> None:
        issues = validate_manuscript(
            "\\section{Intro} Covered~\\cite{Primary,Other}.",
            citation_map=_alias_citation_map(),
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )

        self.assertNotIn("citation_coverage_insufficient", {issue.code for issue in issues})

    def test_citation_coverage_does_not_double_count_alias_and_canonical_equivalent(self) -> None:
        issues = validate_manuscript(
            "\\section{Intro} Alias duplicate coverage~\\cite{Primary,Alias}.",
            citation_map={
                "Primary": {"canonical_bibtex_key": "Primary", "citation_key_role": "canonical"},
                "Alias": {"canonical_bibtex_key": "Primary", "citation_key_role": "alias"},
                "Other": {"canonical_bibtex_key": "Other", "citation_key_role": "canonical"},
            },
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        coverage_issue = next(issue for issue in issues if issue.code == "citation_coverage_insufficient")

        self.assertIn("cited 1 verified papers", coverage_issue.message)
        self.assertIn("need at least 2", coverage_issue.message)

    def test_validate_manuscript_rejects_noncanonical_alias_citations_without_mutating(self) -> None:
        latex = "\\section{Intro} Alias citation~\\cite{Alias}."

        issues = validate_manuscript(
            latex,
            citation_map=_alias_citation_map(),
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        canonical_latex, _ = canonicalize_citation_keys(latex, _alias_citation_map())
        canonical_issues = validate_manuscript(
            canonical_latex,
            citation_map=_alias_citation_map(),
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )

        alias_issues = [issue for issue in issues if issue.code == "noncanonical_citation_aliases"]
        self.assertEqual(len(alias_issues), 1)
        self.assertEqual(alias_issues[0].severity, "error")
        self.assertNotIn("noncanonical_citation_aliases", {issue.code for issue in canonical_issues})
        self.assertEqual(latex, "\\section{Intro} Alias citation~\\cite{Alias}.")

    def test_record_current_validation_report_surfaces_noncanonical_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Alias,Other")

            _path, payload = record_current_validation_report(root, name="validation.alias.json")

            alias_issues = [issue for issue in payload["issues"] if issue["code"] == "noncanonical_citation_aliases"]
            self.assertFalse(payload["ok"])
            self.assertEqual(len(alias_issues), 1)
            self.assertEqual(alias_issues[0]["severity"], "error")
            self.assertGreaterEqual(payload["blocking_issue_count"], 1)

    def test_minimum_citation_backfill_uses_canonical_keys_only(self) -> None:
        rendered = _ensure_minimum_citation_coverage(
            "\\section{Related Work}\nAlready cites~\\cite{Other}.\n\\section{Method}\nBody.\n",
            _alias_citation_map(),
            target=2,
        )

        self.assertIn("\\cite{Primary}", rendered)
        self.assertNotIn("\\cite{Alias}", rendered)

    def test_prompt_and_selected_section_views_do_not_expose_alias_as_independent_paper(self) -> None:
        compact = _compact_citation_map_for_prompt(_alias_citation_map())
        selected = _citation_map_for_selected_sections(
            "\\section{Related Work}\nAlias only~\\cite{Alias}.\n\\section{Method}\nBody.\n",
            _alias_citation_map(),
            ["Related Work"],
        )

        self.assertIn("Primary", compact)
        self.assertNotIn("Alias", compact)
        self.assertIn("Primary", selected)
        self.assertNotIn("Alias", selected)

    def test_fidelity_partition_eval_and_surface_health_use_canonical_reference_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            state = _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent

            partition_path = _ensure_default_citation_partition_request(load_session(root), artifact_dir)
            surface = _citation_surface_health(load_session(root))
            summary = build_session_eval_summary(root)

            self.assertIsNotNone(partition_path)
            partition = json.loads(Path(partition_path).read_text(encoding="utf-8"))
            self.assertEqual(partition["reference_count"], 2)
            self.assertEqual(partition["references_str"].count("Primary Source"), 1)
            self.assertEqual(partition["references_str"].count("Other Source"), 1)
            self.assertEqual(summary["verified_citation_count"], 2)
            self.assertNotIn("references.bib is missing registry key(s): Alias", surface["issues"])
            self.assertEqual(set(surface["references_bib_keys"]), {"Primary", "Other"})
            self.assertNotIn("Alias", surface["references_bib_keys"])
            self.assertNotIn("AliasCPG2024", surface["references_bib_keys"])

    def test_rendered_reference_audit_passes_with_canonical_only_bibtex_and_alias_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary,Other")

            audit = build_rendered_reference_audit(root)

            self.assertEqual(audit["status"], "pass")
            self.assertNotIn("rendered_reference_duplicate_identity", audit["failing_codes"])
            self.assertEqual(set(audit["visible_reference_keys"]), {"Primary", "Other"})
            self.assertNotIn("Alias", audit["bib_keys"])

    def test_cli_full_fidelity_partition_request_uses_canonical_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")

            paths = _write_full_fidelity_artifacts(root, reference_case=None)
            partition = json.loads(Path(paths["citation_partition_request"]).read_text(encoding="utf-8"))

            self.assertEqual(partition["reference_count"], 2)
            self.assertIn("Primary Source", partition["references_str"])
            self.assertIn("Other Source", partition["references_str"])
            self.assertEqual(partition["references_str"].count("Primary Source"), 1)

    def test_narrative_planning_uses_canonical_key_when_alias_appears_first(self) -> None:
        citation_map = _alias_citation_map()

        self.assertEqual(_first_key(citation_map), "Primary")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            _narrative, claim_map, _placements = build_planning_payloads(root)

            positioning_claim = next(item for item in claim_map["claims"] if item["claim_type"] == "positioning")
            self.assertEqual(positioning_claim["source_refs"], [load_session(root).artifacts.citation_map_json])
            anchors = positioning_claim.get("evidence_anchors") or []
            self.assertTrue(anchors)
            excerpt = anchors[0].get("evidence_excerpt", "")
            self.assertIn('"citation_key_role": "canonical"', excerpt)
            self.assertNotIn('"citation_key_role": "alias"', excerpt)

    def test_repair_citation_claims_canonicalizes_candidate_before_validation_and_write(self) -> None:
        class AliasRepairProvider(BaseProvider):
            name = "alias-repair"

            def complete(self, request: CompletionRequest) -> str:
                return (
                    "```latex\n"
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\n"
                    "Primary source supports this background~\\cite{Alias}.\n"
                    "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "Needs repair~\\cite{Primary}.",
                                "citation_keys": ["Primary"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Use source-supported wording.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )
            validation_inputs: list[str] = []

            def fake_validation(cwd, *, name="validation.citation-repair.json"):
                paper_path = Path(load_session(cwd).artifacts.paper_full_tex)
                validation_inputs.append(paper_path.read_text(encoding="utf-8"))
                return artifact_path(cwd, name), {"ok": True, "blocking_issue_count": 0}

            with patch("paperorchestra.ralph_bridge_repair.record_current_validation_report", side_effect=fake_validation):
                with patch("paperorchestra.ralph_bridge_repair._candidate_semantic_recheck", return_value={"status": "pass"}):
                    result = repair_citation_claims(root, AliasRepairProvider(), citation_review_path=review_path)

            candidate_text = Path(result["candidate_path"]).read_text(encoding="utf-8")
            self.assertTrue(result["accepted"])
            self.assertIn("\\cite{Primary}", candidate_text)
            self.assertNotIn("\\cite{Alias}", candidate_text)
            self.assertTrue(validation_inputs)
            self.assertIn("\\cite{Primary}", validation_inputs[0])
            self.assertNotIn("\\cite{Alias}", validation_inputs[0])

    def test_write_intro_related_prompt_counts_and_output_use_canonical_keys(self) -> None:
        class AliasIntroProvider(BaseProvider):
            name = "alias-intro"

            def __init__(self) -> None:
                self.prompt = ""
                self.system_prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                self.system_prompt = request.system_prompt
                return (
                    "```latex\n"
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro~\\cite{Alias,Other}.\n"
                    "\\section{Related Work}\nRelated.\n"
                    "\\section{Method}\nMethod.\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            provider = AliasIntroProvider()
            with patch("paperorchestra.pipeline.collect_paper_contract_issues", return_value=[]):
                path = write_intro_related(root, provider)

            checklist = json.loads(_data_block(provider.prompt, "citation_checklist"))
            self.assertEqual(checklist, ["Other", "Primary"])
            self.assertEqual(_data_block(provider.prompt, "paper_count"), "2")
            self.assertEqual(_data_block(provider.prompt, "min_cite_paper_count"), "2")
            self.assertIn("2", provider.system_prompt)
            output = Path(path).read_text(encoding="utf-8")
            self.assertIn("Primary", output)
            self.assertIn("Other", output)
            self.assertNotIn("Alias", output)

    def test_write_sections_refinement_prompt_target_and_output_use_canonical_keys(self) -> None:
        class AliasSectionProvider(BaseProvider):
            name = "alias-section"

            def __init__(self) -> None:
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return (
                    "```latex\n"
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro~\\cite{Primary}.\n"
                    "\\section{Related Work}\nRelated~\\cite{Other}.\n"
                    "\\section{Method}\nMethod update~\\cite{alias,Other}.\n"
                    "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary,Other")
            provider = AliasSectionProvider()
            with patch("paperorchestra.pipeline.collect_paper_contract_issues", return_value=[]):
                path = write_sections(root, provider, only_sections=["Method"])

            coverage = json.loads(_data_block(provider.prompt, "citation_coverage_target.json"))
            prompt_map = json.loads(_data_block(provider.prompt, "citation_map.json"))
            self.assertEqual(coverage["available_verified_citations"], 2)
            self.assertIn("Primary", prompt_map)
            self.assertNotIn("Alias", prompt_map)
            text = Path(path).read_text(encoding="utf-8")
            cited_keys = extract_citation_keys(text)
            self.assertIn("Primary", cited_keys)
            self.assertIn("Other", cited_keys)
            self.assertNotIn("Alias", cited_keys)
            self.assertNotIn("alias", cited_keys)
            self.assertNotIn("AliasCPG2024", cited_keys)

    def test_review_current_paper_uses_canonical_prompt_map_and_average(self) -> None:
        class ReviewProvider(BaseProvider):
            name = "review-provider"

            def __init__(self) -> None:
                self.prompt = ""
                self.system_prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                self.system_prompt = request.system_prompt
                return _review_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary,Other")
            provider = ReviewProvider()

            review_current_paper(root, provider)

            prompt_map = json.loads(_data_block(provider.prompt, "citation_map.json"))
            self.assertEqual(set(prompt_map), {"Primary", "Other"})
            self.assertIn("Reference Average Citation Count: 2", provider.system_prompt)

    def test_refine_current_paper_candidate_only_canonicalizes_alias_before_candidate_artifact(self) -> None:
        class AliasRefineProvider(BaseProvider):
            name = "alias-refine"

            def complete(self, request: CompletionRequest) -> str:
                return (
                    '```json\n{"actions_taken":["updated"],"addressed_weaknesses":[],"integrated_answers":[]}\n```\n'
                    "```latex\n"
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro~\\cite{Primary}.\n"
                    "\\section{Related Work}\nRelated~\\cite{Other}.\n"
                    "\\section{Method}\nRefined method~\\cite{alias,Other}.\n"
                    "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            state = _write_alias_citation_artifacts(root, manuscript_cites="Primary,Other")
            review_path = artifact_path(root, "review.latest.json")
            review_path.write_text(_review_json(score=70), encoding="utf-8")
            state.artifacts.latest_review_json = str(review_path)
            save_session(root, state)

            with patch("paperorchestra.pipeline.collect_paper_contract_issues", return_value=[]):
                with patch("paperorchestra.pipeline.review_current_paper", return_value=review_path):
                    results = refine_current_paper(root, AliasRefineProvider(), candidate_only=True)

            candidate_text = Path(results[0]["candidate_path"]).read_text(encoding="utf-8")
            cited_keys = extract_citation_keys(candidate_text)
            self.assertIn("Primary", cited_keys)
            self.assertIn("Other", cited_keys)
            self.assertNotIn("Alias", cited_keys)
            self.assertNotIn("alias", cited_keys)
            self.assertNotIn("AliasCPG2024", cited_keys)

    def test_repair_prompt_uses_canonical_allowed_entries_and_unknown_still_rejected(self) -> None:
        class PromptThenUnknownProvider(BaseProvider):
            name = "repair-prompt-unknown"

            def __init__(self) -> None:
                self.prompt = ""

            def complete(self, request: CompletionRequest) -> str:
                self.prompt = request.user_prompt
                return (
                    "```latex\n"
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nBad citation~\\cite{FakeNew}.\n"
                    "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                    "\\end{document}\n"
                    "```"
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "Needs repair~\\cite{Primary}.",
                                "citation_keys": ["Primary"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Use source-supported wording.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )
            provider = PromptThenUnknownProvider()

            result = repair_citation_claims(root, provider, citation_review_path=review_path)

            prompt_map = json.loads(_data_block(provider.prompt, "citation_map.json"))
            self.assertEqual(set(prompt_map), {"Primary", "Other"})
            self.assertFalse(result["accepted"])
            self.assertEqual(result["reason"], "unknown_citation_keys")
            self.assertEqual(result["unknown_citation_keys"], ["FakeNew"])

    def test_fidelity_surface_health_reports_missing_canonical_bib_and_missing_alias_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_alias_citation_artifacts(root, manuscript_cites="Primary")
            state = load_session(root)
            Path(state.artifacts.references_bib).write_text("@article{Other, title={Other Source}, author={B. Author}, year={2023}}\n", encoding="utf-8")
            missing_bib = _citation_surface_health(load_session(root))

            Path(state.artifacts.references_bib).write_text(
                "@article{Primary, title={Primary Source}, author={A. Author}, year={2024}}\n"
                "@article{Other, title={Other Source}, author={B. Author}, year={2023}}\n",
                encoding="utf-8",
            )
            citation_map = _alias_citation_map()
            citation_map.pop("Alias")
            Path(state.artifacts.citation_map_json).write_text(json.dumps(citation_map), encoding="utf-8")
            missing_alias = _citation_surface_health(load_session(root))

            self.assertTrue(any(issue.startswith("references.bib is missing registry key(s):") and "Primary" in issue for issue in missing_bib["issues"]))
            self.assertTrue(any("citation_map.json" in issue and "Alias" in issue for issue in missing_alias["issues"]))

    def test_legacy_maps_and_non_alias_keys_keep_existing_canonicalization_behavior(self) -> None:
        latex, replacements = canonicalize_citation_keys("\\cite{RFC9001,Other}.", {"Rfc9001": {}, "Other": {}})

        self.assertIn("\\cite{Rfc9001, Other}", latex)
        self.assertEqual(replacements, {"RFC9001": "Rfc9001"})

    def test_alias_only_map_allows_canonical_key_after_rewrite_without_accepting_raw_alias(self) -> None:
        alias_only_map = {
            "Alias": {
                "title": "Primary Source",
                "canonical_bibtex_key": "Primary",
                "alias_bibtex_keys": ["Alias"],
                "citation_key_role": "alias",
            }
        }

        canonical_text, replacements = canonicalize_citation_keys("Background~\\cite{Alias}.", alias_only_map)
        self.assertIn("\\cite{Primary}", canonical_text)
        self.assertEqual(replacements, {"Alias": "Primary"})

        canonical_issues = validate_manuscript(
            canonical_text,
            citation_map=alias_only_map,
            figures_dir=None,
        )
        self.assertNotIn("unknown_citation_keys", {issue.code for issue in canonical_issues})
        self.assertNotIn("noncanonical_citation_aliases", {issue.code for issue in canonical_issues})
        self.assertNotIn("citation_coverage_insufficient", {issue.code for issue in canonical_issues})

        raw_alias_issues = validate_manuscript(
            "Background~\\cite{Alias}.",
            citation_map=alias_only_map,
            figures_dir=None,
        )
        self.assertIn("noncanonical_citation_aliases", {issue.code for issue in raw_alias_issues})

        kept_text, dropped = _drop_unknown_citation_keys(canonical_text, alias_only_map)
        self.assertIn("\\cite{Primary}", kept_text)
        self.assertEqual(dropped, {})
        self.assertEqual(_ensure_minimum_citation_coverage(canonical_text, alias_only_map), canonical_text)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            state = load_session(root)
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(json.dumps(alias_only_map), encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\nCanonical~\\cite{Primary}.\n\\end{document}\n",
                encoding="utf-8",
            )
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.paper_full_tex = str(paper_path)
            save_session(root, state)

            titles = build_generated_citation_titles(root)

            self.assertEqual(titles["cited_keys"], ["Primary"])
            self.assertEqual(titles["generated_titles"], ["Primary Source"])

            class AliasOnlyRepairProvider(BaseProvider):
                name = "alias-only-repair"

                def complete(self, request: CompletionRequest) -> str:
                    return (
                        "```latex\n"
                        "\\documentclass{article}\n\\begin{document}\n"
                        "Repaired~\\cite{Alias}.\n"
                        "\\bibliographystyle{plain}\n\\bibliography{references}\n"
                        "\\end{document}\n"
                        "```"
                    )

            review_path = artifact_path(root, "citation_support_review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "cite-001",
                                "sentence": "Needs repair~\\cite{Primary}.",
                                "citation_keys": ["Primary"],
                                "support_status": "unsupported",
                                "risk": "high",
                                "suggested_fix": "Use source-supported wording.",
                            }
                        ],
                        "summary": {"unsupported": 1},
                    }
                ),
                encoding="utf-8",
            )

            repair_result = repair_citation_claims(root, AliasOnlyRepairProvider(), citation_review_path=review_path)

            self.assertEqual(repair_result["unknown_citation_keys"], [])
            candidate_text = Path(repair_result["candidate_path"]).read_text(encoding="utf-8")
            self.assertIn("\\cite{Primary}", candidate_text)
            self.assertNotIn("\\cite{Alias}", candidate_text)


if __name__ == "__main__":
    unittest.main()
