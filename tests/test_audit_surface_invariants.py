from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.citation_integrity import (
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
    write_citation_integrity_audit,
    write_rendered_reference_audit,
)
from paperorchestra.critics import write_citation_support_review, write_section_review
from paperorchestra.fidelity import build_reproducibility_audit, run_fidelity_audit
from paperorchestra.models import InputBundle, ScoreSnapshot
from paperorchestra.pipeline import (
    _accept_review_delta,
    import_prior_work,
    plan_narrative_and_claims,
    record_current_validation_report,
    record_fidelity_report,
    refine_current_paper,
    run_pipeline,
    write_figure_placement_review,
)
from paperorchestra.providers import MockProvider, ShellProvider, get_citation_support_provider
from paperorchestra.quality_loop import write_quality_eval, write_quality_loop_plan
from paperorchestra.runtime_parity import record_lane_manifest
from paperorchestra.session import artifact_path, create_session, load_session, runtime_root, save_session
from paperorchestra.source_obligations import build_source_obligations, write_source_obligations


class AuditSurfaceInvariantTests(unittest.TestCase):
    def _init_session_with_minimal_inputs(self, root: Path):
        files = {
            "idea.md": "## Problem Statement\nDemo\n",
            "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
            "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
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
                cutoff_date="2024-11-01",
            ),
        )

    def test_fidelity_rollup_stays_partial_when_some_checks_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            _, payload = record_fidelity_report(root)
            self.assertEqual(payload["overall_status"], "partial")
            self.assertGreater(payload["status_histogram"]["implemented"], 0)
            self.assertGreater(payload["status_histogram"]["missing"], 0)
            self.assertIn(payload["summary_descriptor"], {"mostly_implemented", "degraded", "partial"})

    def test_reproducibility_warns_when_live_verification_was_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RFC9001,\n"
                "  title = {Using TLS to Secure QUIC},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee prior work~\\cite{RFC9001}.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            save_session(root, state)

            with patch.dict(os.environ, {"PAPERO_STRICT_CONTENT_GATES": ""}, clear=False):
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
                payload = build_reproducibility_audit(root)
            self.assertFalse(payload["verification_invoked"])
            self.assertEqual(payload["verdict"], "WARN")
            self.assertTrue(any("never invoked" in reason for reason in payload["warning_reasons"]))

            strict_payload = build_reproducibility_audit(root, require_live_verification=True)
            self.assertEqual(strict_payload["verdict"], "BLOCK")
            self.assertTrue(any("required for this audit" in reason for reason in strict_payload["blocking_reasons"]))

    def test_required_live_verification_blocks_seed_only_registry_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "key": "SeedOnly2026",
                            "title": "Curated seed only",
                            "paper_id": "S2-SEED",
                            "origin": "metadata_seed_for_live_verification",
                        },
                        {
                            "key": "Matched2026",
                            "title": "Live matched",
                            "paper_id": "S2-LIVE",
                            "origin": "metadata_seed_for_live_verification+macro_candidates",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"SeedOnly2026": {}, "Matched2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text(
                "@article{SeedOnly2026,title={Curated seed only},year={2026}}\n"
                "@article{Matched2026,title={Live matched},year={2026}}\n",
                encoding="utf-8",
            )
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "See~\\cite{SeedOnly2026,Matched2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            self.assertEqual(payload["citation_live_provenance"]["registry_count"], 2)
            self.assertEqual(payload["citation_live_provenance"]["live_verified_count"], 1)
            self.assertEqual(payload["citation_live_provenance"]["seed_only_count"], 1)
            self.assertEqual(payload["citation_live_provenance"]["status"], "curated")
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertTrue(
                any("seed-only or curated metadata without live verification" in reason for reason in payload["blocking_reasons"])
            )

    def test_required_live_verification_ignores_unused_curated_registry_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "UnusedCurated2026",
                            "title": "Unused curated entry",
                            "paper_id": "S2-SEED",
                            "origin": "metadata_seed_for_live_verification",
                        },
                        {
                            "bibtex_key": "Matched2026",
                            "alias_bibtex_keys": ["MatchedAlias2026"],
                            "title": "Live matched",
                            "paper_id": "S2-LIVE",
                            "origin": "metadata_seed_for_live_verification+macro_candidates",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"UnusedCurated2026": {}, "Matched2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text(
                "@article{UnusedCurated2026,title={Unused curated entry},year={2026}}\n"
                "@article{Matched2026,title={Live matched},year={2026}}\n",
                encoding="utf-8",
            )
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Only the live alias is cited~\\cite{MatchedAlias2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            provenance = payload["citation_live_provenance"]
            self.assertEqual(provenance["registry_count"], 2)
            self.assertEqual(provenance["cited_entry_count"], 1)
            self.assertEqual(provenance["unused_registry_count"], 1)
            self.assertEqual(provenance["cited_live_verified_count"], 1)
            self.assertEqual(provenance["cited_curated_seed_count"], 0)
            self.assertEqual(provenance["status"], "live")
            self.assertFalse(
                any("seed-only or curated metadata without live verification" in reason for reason in payload["blocking_reasons"])
            )

    def test_required_live_verification_ignores_unused_mock_registry_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "UnusedMock2026",
                            "title": "Unused mock entry",
                            "paper_id": "mock-unused",
                            "authors": ["Mock Author"],
                            "venue": "Mock Venue",
                        },
                        {
                            "bibtex_key": "Matched2026",
                            "title": "Live matched",
                            "paper_id": "S2-LIVE",
                            "origin": "metadata_seed_for_live_verification+macro_candidates",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"UnusedMock2026": {}, "Matched2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text(
                "@article{UnusedMock2026,title={Unused mock entry},year={2026}}\n"
                "@article{Matched2026,title={Live matched},year={2026}}\n",
                encoding="utf-8",
            )
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "Only the live source is cited~\\cite{Matched2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            provenance = payload["citation_live_provenance"]
            self.assertEqual(payload["mock_registry_entry_count"], 1)
            self.assertEqual(provenance["mock_entry_count"], 1)
            self.assertEqual(provenance["cited_mock_count"], 0)
            self.assertEqual(provenance["unused_registry_count"], 1)
            self.assertEqual(provenance["status"], "live")
            self.assertFalse(any("mock entry" in reason for reason in payload["blocking_reasons"]))

    def test_required_live_verification_blocks_cited_mock_registry_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "MockCited2026",
                            "title": "Mock cited entry",
                            "paper_id": "mock-cited",
                            "authors": ["Mock Author"],
                            "venue": "Mock Venue",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"MockCited2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{MockCited2026,title={Mock cited entry},year={2026}}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "The draft cites mock evidence~\\cite{MockCited2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            provenance = payload["citation_live_provenance"]
            self.assertEqual(provenance["status"], "mock")
            self.assertEqual(provenance["cited_mock_count"], 1)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertTrue(any("cited citation registry contains 1 mock" in reason.lower() for reason in payload["blocking_reasons"]))

    def test_required_live_verification_reports_mixed_cited_provenance_distinctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "MixedSource2026",
                            "title": "Authoritative source",
                            "paper_id": "DOC-1",
                            "origin": "operator_authoritative_source",
                            "url": "https://example.invalid/source",
                            "external_ids": {"DOI": "10.1000/example"},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"MixedSource2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@misc{MixedSource2026,title={Authoritative source},year={2026}}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "A claim cites mixed provenance~\\cite{MixedSource2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            provenance = payload["citation_live_provenance"]
            self.assertEqual(provenance["status"], "mixed")
            self.assertEqual(provenance["cited_mixed_count"], 1)
            self.assertEqual(provenance["cited_curated_seed_count"], 0)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertTrue(any("mixed cited provenance" in reason for reason in payload["blocking_reasons"]))
            self.assertFalse(
                any("seed-only or curated metadata without live verification" in reason for reason in payload["blocking_reasons"])
            )

    def test_metadata_seed_with_external_ids_remains_curated_without_live_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "SeedWithExternalId2026",
                            "title": "Seed with external identifier",
                            "paper_id": "S2-SEED",
                            "origin": "metadata_seed_for_live_verification",
                            "url": "https://example.invalid/seed",
                            "external_ids": {"DOI": "10.1000/seed"},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text('{"SeedWithExternalId2026": {}}', encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{SeedWithExternalId2026,title={Seed with external identifier},year={2026}}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "A claim cites metadata seed evidence~\\cite{SeedWithExternalId2026}.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root, require_live_verification=True)

            provenance = payload["citation_live_provenance"]
            self.assertEqual(provenance["status"], "curated")
            self.assertEqual(provenance["cited_curated_seed_count"], 1)
            self.assertEqual(provenance["cited_mixed_count"], 0)

    def test_empty_citation_artifacts_downgrade_fidelity_and_block_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text("[]", encoding="utf-8")
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text("{}", encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            record_lane_manifest(
                root,
                stage="verify",
                role="Citation Verification",
                runtime_mode="compatibility",
                lane_type="python",
                owner="operator",
                status="completed",
                input_artifacts=[],
                output_artifacts=[str(registry_path), str(citation_map_path), str(references_path)],
                fallback_used=False,
                notes=["Verification lane marked completed for regression coverage."],
            )
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            _, fidelity_payload = record_fidelity_report(root)
            fidelity_checks = {item["code"]: item for item in fidelity_payload["checks"]}
            self.assertEqual(fidelity_checks["verified_citation_lane"]["status"], "partial")

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertTrue(any("lane completed" in reason.lower() for reason in payload["blocking_reasons"]))
            self.assertIn("citation_registry.json is empty.", payload["citation_artifact_issues"])
            self.assertIn("citation_map.json is empty.", payload["citation_artifact_issues"])

    def test_nonempty_curated_citation_artifacts_do_not_trigger_false_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RFC9001,\n"
                "  title = {Using TLS to Secure QUIC},\n"
                "  author = {Martin Thomson and Sean Turner},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee prior work~\\cite{RFC9001}.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            save_session(root, state)

            _, fidelity_payload = record_fidelity_report(root)
            fidelity_checks = {item["code"]: item for item in fidelity_payload["checks"]}
            self.assertEqual(fidelity_checks["verified_citation_lane"]["status"], "implemented")

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["citation_registry_entry_count"], 1)
            self.assertEqual(payload["citation_map_entry_count"], 1)
            self.assertEqual(payload["references_bib_entry_count"], 1)
            self.assertFalse(payload["citation_artifact_issues"])
            self.assertFalse(any("malformed" in reason.lower() for reason in payload["blocking_reasons"]))

    def test_malformed_nonempty_citation_artifacts_are_not_treated_as_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text('["junk"]', encoding="utf-8")
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(json.dumps({"RFC9001": "bad"}), encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{RFC9001,\n  title={Using TLS to Secure QUIC}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            record_lane_manifest(
                root,
                stage="verify",
                role="Citation Verification",
                runtime_mode="compatibility",
                lane_type="python",
                owner="operator",
                status="completed",
                input_artifacts=[],
                output_artifacts=[str(registry_path), str(citation_map_path), str(references_path)],
                fallback_used=False,
                notes=["Verification lane marked completed for malformed-artifact regression coverage."],
            )
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            _, fidelity_payload = record_fidelity_report(root)
            fidelity_checks = {item["code"]: item for item in fidelity_payload["checks"]}
            self.assertEqual(fidelity_checks["verified_citation_lane"]["status"], "partial")

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertTrue(any("malformed" in issue for issue in payload["citation_artifact_issues"]))

    def test_unreadable_bibtex_path_degrades_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-1",
                            "title": "Using TLS to Secure QUIC",
                            "year": 2021,
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": ["Martin Thomson"],
                            "citation_count": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC"}}),
                encoding="utf-8",
            )
            references_dir = artifact_path(root, "references.bib")
            references_dir.unlink(missing_ok=True)
            references_dir.mkdir()
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_dir)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertIn("references.bib is unreadable or malformed.", payload["citation_artifact_issues"])

    def test_type_invalid_registry_entries_are_treated_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-1",
                            "title": "Using TLS to Secure QUIC",
                            "year": "2021",
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": "Martin Thomson",
                            "citation_count": "12",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC"}}),
                encoding="utf-8",
            )
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{RFC9001,\n  title={Using TLS to Secure QUIC}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertIn("citation_registry.json contains malformed entries (1 invalid).", payload["citation_artifact_issues"])

    def test_float_typed_integer_fields_are_treated_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-1",
                            "title": "Using TLS to Secure QUIC",
                            "year": 2021.5,
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": ["Martin Thomson"],
                            "citation_count": 12.5,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC", "year": 2021.5}}),
                encoding="utf-8",
            )
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{RFC9001,\n  title={Using TLS to Secure QUIC}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            self.assertIn("citation_registry.json contains malformed entries (1 invalid).", payload["citation_artifact_issues"])
            self.assertIn("citation_map.json contains malformed entries (1 invalid).", payload["citation_artifact_issues"])

    def test_semantic_scholar_integer_external_ids_are_valid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-1",
                            "title": "Using TLS to Secure QUIC",
                            "year": 2021,
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": ["Martin Thomson"],
                            "citation_count": 12,
                            "external_ids": {"CorpusId": 68091580, "DOI": "10.17487/RFC9001"},
                            "bibtex_key": "RFC9001",
                            "alias_bibtex_keys": [],
                            "title_match_ratio": 100.0,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"RFC9001": {"title": "Using TLS to Secure QUIC", "paper_id": "paper-1", "year": 2021}}),
                encoding="utf-8",
            )
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{RFC9001,\n  title={Using TLS to Secure QUIC}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\citep{RFC9001}.\n\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)

            self.assertNotIn("citation_registry.json contains malformed entries (1 invalid).", payload["citation_artifact_issues"])

    def test_cross_artifact_citation_key_mismatches_block_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-alpha",
                            "title": "Alpha Paper",
                            "year": 2021,
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": ["Alice"],
                            "citation_count": 1,
                            "bibtex_key": "Alpha",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(
                json.dumps({"Beta": {"title": "Beta Paper", "paper_id": "paper-beta"}}),
                encoding="utf-8",
            )
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{Gamma,\n  title={Gamma Paper}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\citep{Beta}.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            joined = "\n".join(payload["citation_artifact_issues"])
            self.assertIn("citation_map.json contains key(s) not present in citation_registry.json: Beta", joined)
            self.assertIn("references.bib contains key(s) not present in citation_registry.json: Gamma", joined)
            self.assertIn("manuscript cites key(s) missing from references.bib: Beta", joined)

    def test_keyless_registry_and_bibtex_entries_are_treated_as_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            registry_path = artifact_path(root, "citation_registry.json")
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "paper-alpha",
                            "title": "Alpha Paper",
                            "year": 2021,
                            "publication_date": None,
                            "venue": "RFC",
                            "abstract": "Demo",
                            "authors": ["Alice"],
                            "citation_count": 1,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            citation_map_path = artifact_path(root, "citation_map.json")
            citation_map_path.write_text(json.dumps({"Alpha": {"title": "Alpha Paper"}}), encoding="utf-8")
            references_path = artifact_path(root, "references.bib")
            references_path.write_text("@article{,\n  title={Alpha Paper}\n}\n", encoding="utf-8")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\cite{Alpha}.\n\\end{document}\n",
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.citation_registry_json = str(registry_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            state.artifacts.references_bib = str(references_path)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            state.latest_verify_mode = "live"
            save_session(root, state)

            payload = build_reproducibility_audit(root)
            self.assertEqual(payload["verdict"], "BLOCK")
            joined = "\n".join(payload["citation_artifact_issues"])
            self.assertIn("citation_registry.json contains malformed entries", joined)
            self.assertIn("references.bib contains BibTeX entries without extractable keys.", joined)

    def test_run_pipeline_is_not_blocked_after_accept_then_reject_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            with patch(
                "paperorchestra.pipeline.refine_current_paper",
                return_value=[
                    {"iteration": 1, "accepted": True, "validation_report_path": "validation.refine.iter-01.json"},
                    {"iteration": 2, "accepted": False, "validation_report_path": "validation.refine.iter-02.json"},
                ],
            ):
                result = run_pipeline(
                    root,
                    provider=MockProvider(),
                    discovery_mode="model",
                    verify_mode="mock",
                    refine_iterations=2,
                    compile_paper=False,
                )
            state = load_session(root)
            self.assertEqual([item["accepted"] for item in result["refine"]], [True, False])
            self.assertEqual(result["status"], "draft_complete")
            self.assertEqual(state.current_phase, "draft_complete")

    def test_compile_preservation_is_recorded_as_distinct_outcome_and_audit_warning(self) -> None:
        class CompileBreakingRefiner(MockProvider):
            def complete(self, request: CompletionRequest) -> str:
                system = request.system_prompt.lower()
                if "content refinement agent" in system:
                    return """```latex
\\documentclass{article}
\\begin{document}
\\section{Introduction}
Compile-breaking refinement.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=1, compile_paper=False)
            state = load_session(root)
            compile_report = root / "compile-report.json"
            compile_report.write_text(
                json.dumps(
                    {
                        "pdf_path": str(root / "paper.full.pdf"),
                        "log_path": str(root / "latex-build.log"),
                        "return_code": 0,
                        "pdf_exists": True,
                        "clean": True,
                        "warning_summary": [],
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.compiled_pdf = str(root / "paper.full.pdf")
            save_session(root, state)

            with patch("paperorchestra.pipeline.compile_latex", side_effect=RuntimeError("compile failed")):
                result = refine_current_paper(root, CompileBreakingRefiner(), iterations=1, require_compile_for_accept=True)

            audit = build_reproducibility_audit(root)
            self.assertTrue(result[0]["accepted"])
            self.assertTrue(result[0]["preservation"])
            self.assertEqual(result[0]["reason"], "compile_failed_preserved_previous")
            self.assertEqual(audit["refinement_compile_preservation_count"], 1)
            self.assertTrue(any("preserved the prior compiled manuscript" in reason for reason in audit["warning_reasons"]))

    def test_accept_review_delta_rejects_axis_swap_at_same_overall_score(self) -> None:
        accepted = _accept_review_delta(
            70.0,
            70.0,
            {"coverage_and_completeness": 72.0, "organization_and_writing": 68.0},
            {"coverage_and_completeness": 70.0, "organization_and_writing": 70.0},
        )
        self.assertFalse(accepted)

    def test_rejected_refinement_note_is_deduplicated_across_retries(self) -> None:
        class RegressiveProvider(MockProvider):
            def __init__(self) -> None:
                self.review_calls = 0

            def complete(self, request):
                system = request.system_prompt.lower()
                if "skeptical academic reviewer" in system:
                    self.review_calls += 1
                    if self.review_calls == 1:
                        return json.dumps(
                            {
                                "paper_title": "Demo",
                                "citation_statistics": {
                                    "estimated_unique_citations": 10,
                                    "citation_density_assessment": "appropriate",
                                    "breadth_across_subareas": "moderate",
                                    "comparison_to_baseline": "baseline",
                                    "notes": "baseline review",
                                },
                                "axis_scores": {"coverage_and_completeness": {"score": 72, "justification": "baseline"}},
                                "penalties": [],
                                "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                                "questions": [],
                                "overall_score": 72,
                            }
                        )
                    return json.dumps(
                        {
                            "paper_title": "Demo",
                            "citation_statistics": {
                                "estimated_unique_citations": 10,
                                "citation_density_assessment": "appropriate",
                                "breadth_across_subareas": "moderate",
                                "comparison_to_baseline": "worse",
                                "notes": "regressed review",
                            },
                            "axis_scores": {"coverage_and_completeness": {"score": 61, "justification": "worse"}},
                            "penalties": [],
                            "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                            "questions": [],
                            "overall_score": 61,
                        }
                    )
                if "content refinement agent" in system:
                    return """```json
{"addressed_weaknesses":["None"],"integrated_answers":["None"],"actions_taken":["Made it worse"]}
```
```latex
\\documentclass{article}
\\begin{document}
Regressed mock paper.
\\section{Method}
The regressed mock paper keeps enough method text to satisfy structural validation while still losing review score. It mentions a staged pipeline, artifacts, validation, and review gates without improving the manuscript.
\\end{document}
```"""
                return super().complete(request)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            provider = RegressiveProvider()
            run_pipeline(root, provider=provider, discovery_mode="model", verify_mode="mock", refine_iterations=0)
            with patch("paperorchestra.pipeline.collect_paper_contract_issues", return_value=[]):
                refine_current_paper(root, provider, iterations=1)
                refine_current_paper(root, provider, iterations=1)
            state = load_session(root)
            rejection_note = "Rejected refinement iteration 1 (score 72.0 -> 61.0)."
            self.assertEqual(sum(1 for note in state.notes if note == rejection_note), 1)

    def test_run_pipeline_writes_default_citation_partition_request_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=0)
            state = load_session(root)
            artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent
            partition_request = artifact_dir / "citation_partition_request.json"
            self.assertTrue(partition_request.exists())
            fidelity = json.loads(Path(state.artifacts.latest_fidelity_json).read_text(encoding="utf-8"))
            partition_check = next(check for check in fidelity["checks"] if check["code"] == "citation_partition_scaffold_surface")
            self.assertIn(partition_check["status"], {"partial", "implemented"})
            if partition_check["status"] != "implemented":
                self.assertIn("compare-partitioned-citation-coverage", partition_check["next_step"])

    def test_strict_content_gates_block_comparative_claim_warnings(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nDraft cites~\\cite{RFC9001}.\n\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                            "issues": [
                                {
                                    "code": "unsupported_comparative_claim",
                                    "severity": "warning",
                                    "message": "Manuscript contains comparative claims not evidenced in the experimental log: better than",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)

                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
                non_strict = build_reproducibility_audit(root)
                self.assertEqual(non_strict["verdict"], "WARN")
                self.assertFalse(non_strict["strict_content_gates"])

                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
                strict = build_reproducibility_audit(root)
                self.assertEqual(strict["verdict"], "BLOCK")
                self.assertTrue(strict["strict_content_gates"])
                self.assertEqual(strict["strict_content_gate_issues"][0]["code"], "unsupported_comparative_claim")
                self.assertTrue(any("Strict content gates blocked" in reason for reason in strict["blocking_reasons"]))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_strict_content_gates_ignore_stale_validation_reports(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\cite{RFC9001}. This is better than an unlisted baseline.\n\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                old_validation = artifact_path(root, "validation.refine.iter-01.json")
                old_validation.write_text(
                    json.dumps(
                        {
                            "stage": "refinement",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                            "issues": [
                                {
                                    "code": "unsupported_comparative_claim",
                                    "severity": "warning",
                                    "message": "Old warning",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                clean_validation = artifact_path(root, "validation.refine.iter-02.json")
                clean_validation.write_text(
                    json.dumps({"stage": "refinement", "ok": True, "blocking_issue_count": 0, "warning_count": 0, "issues": []}),
                    encoding="utf-8",
                )
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_validation_json = str(clean_validation)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                payload = build_reproducibility_audit(root)
                self.assertFalse(
                    any(issue["code"] == "unsupported_comparative_claim" for issue in payload["strict_content_gate_issues"])
                )
                self.assertTrue(any(issue["code"] == "validation_report_stale" for issue in payload["strict_content_gate_issues"]))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_strict_content_gates_block_tail_clump_after_figure_review(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = self._init_session_with_minimal_inputs(root)
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro text.\n"
                    + "\n".join(f"Filler line {idx}." for idx in range(20))
                    + "\n\\section{Results}\n"
                    + "\n".join(f"Late filler {idx}." for idx in range(120))
                    + "\nSee Figure~\\ref{fig:late1} and Figure~\\ref{fig:late2}.\n"
                    "\\begin{figure}[t]\n\\caption{Late one}\n\\label{fig:late1}\n\\end{figure}\n"
                    "\\begin{figure}[t]\n\\caption{Late two}\n\\label{fig:late2}\n\\end{figure}\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                _, figure_payload = write_figure_placement_review(root)
                self.assertIn("tail_clump", figure_payload["summary"]["warning_codes"])

                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"
                strict = build_reproducibility_audit(root)
                self.assertEqual(strict["verdict"], "BLOCK")
                self.assertTrue(any(issue["code"] == "tail_clump" for issue in strict["strict_content_gate_issues"]))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_strict_content_gates_block_missing_figure_review(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = self._init_session_with_minimal_inputs(root)
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nSee Figure~\\ref{fig:late1} and Figure~\\ref{fig:late2}.\n"
                    + "\n".join(f"Filler line {idx}." for idx in range(120))
                    + "\n\\begin{figure}[t]\n\\caption{Late one}\n\\label{fig:late1}\n\\end{figure}\n"
                    "\\begin{figure}[t]\n\\caption{Late two}\n\\label{fig:late2}\n\\end{figure}\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                payload = build_reproducibility_audit(root)
                self.assertEqual(payload["verdict"], "BLOCK")
                self.assertTrue(any(issue["code"] == "figure_placement_review_missing" for issue in payload["strict_content_gate_issues"]))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_loop_plan_classifies_audit_findings_into_repair_actions(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson and Sean Turner},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro cites~\\cite{RFC9001}.\n"
                    + "\n".join(f"Filler line {idx}." for idx in range(120))
                    + "\nThis draft is better than the baseline without a grounded log sentence.\n"
                    "See Figure~\\ref{fig:late1} and Figure~\\ref{fig:late2}.\n"
                    "\\begin{figure}[t]\n\\caption{Late one}\n\\label{fig:late1}\n\\end{figure}\n"
                    "\\begin{figure}[t]\n\\caption{Late two}\n\\label{fig:late2}\n\\end{figure}\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                            "issues": [
                                {
                                    "code": "unsupported_comparative_claim",
                                    "severity": "warning",
                                    "message": "Manuscript contains comparative claims not evidenced in the experimental log: better than",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_validation_json = str(validation_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                path, plan = write_quality_loop_plan(root)
                self.assertTrue(path.exists())
                self.assertEqual(plan["verdict"], "continue")
                self.assertTrue(plan["source_artifacts"]["reproducibility_audit"])
                self.assertTrue(plan["source_artifacts"]["fidelity_audit"])
                self.assertIn("audit_snapshots", plan)
                codes = [action["code"] for action in plan["repair_actions"]]
                self.assertIn("unsupported_comparative_claim", codes)
                self.assertIn("tail_clump", codes)
                self.assertEqual(codes.count("unsupported_comparative_claim"), 1)
                self.assertTrue(plan["next_ralph_instruction"].startswith("Continue"))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_loop_plan_does_not_report_success_on_unresolved_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{RFC9001,\n"
                "  title = {Using TLS to Secure QUIC},\n"
                "  author = {Martin Thomson},\n"
                "  year = {2021}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\cite{RFC9001}.\n\\end{document}\n",
                encoding="utf-8",
            )
            compile_report = artifact_path(root, "compile-report.json")
            compile_report.write_text(json.dumps({"clean": False, "pdf_exists": False}), encoding="utf-8")
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_compile_report_json = str(compile_report)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            state.latest_runtime_mode = "compatibility"
            save_session(root, state)

            _, plan = write_quality_loop_plan(root)
            self.assertIn(plan["verdict"], {"continue", "human_needed"})
            self.assertNotEqual(plan["verdict"], "success")
            self.assertTrue(any(action["code"] == "compile_not_clean" for action in plan["repair_actions"]))

    def test_quality_loop_plan_does_not_create_repair_actions_from_stale_artifacts(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                old_paper = "\\documentclass{article}\n\\begin{document}\nOld better than draft.\\end{document}\n"
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\cite{RFC9001}.\\end{document}\n",
                    encoding="utf-8",
                )
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(old_paper.encode("utf-8")).hexdigest(),
                            "issues": [
                                {
                                    "code": "unsupported_comparative_claim",
                                    "severity": "warning",
                                    "message": "Old unsupported claim.",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                figure_review_path = artifact_path(root, "figure-placement-review.json")
                figure_review_path.write_text(
                    json.dumps(
                        {
                            "manuscript_sha256": hashlib.sha256(old_paper.encode("utf-8")).hexdigest(),
                            "warnings": [{"code": "tail_clump", "message": "Old tail clump."}],
                            "figures": [{"label": "fig:old", "warning_codes": ["tail_clump"]}],
                            "summary": {"warning_codes": ["tail_clump"], "warning_count": 1},
                        }
                    ),
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_validation_json = str(validation_path)
                state.artifacts.latest_figure_placement_review_json = str(figure_review_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                _, plan = write_quality_loop_plan(root)
                codes = [action["code"] for action in plan["repair_actions"]]
                self.assertEqual(plan["verdict"], "continue")
                self.assertNotIn("unsupported_comparative_claim", codes)
                self.assertNotIn("tail_clump", codes)
                self.assertIn("validation_report_stale", codes)
                self.assertIn("figure_placement_review_stale", codes)
                stale_actions = {action["code"]: action for action in plan["repair_actions"]}
                self.assertIn("Regenerate a validation report", stale_actions["validation_report_stale"]["ralph_instruction"])
                self.assertEqual(stale_actions["validation_report_stale"]["suggested_commands"][0], "paperorchestra validate-current")
                self.assertIn("review-figure-placement", " ".join(stale_actions["figure_placement_review_stale"]["suggested_commands"]))
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_eval_short_circuits_after_stale_preconditions(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                old_paper = "\\documentclass{article}\n\\begin{document}\nOld better than draft.\\end{document}\n"
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nSee~\\cite{RFC9001}.\\end{document}\n",
                    encoding="utf-8",
                )
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(old_paper.encode("utf-8")).hexdigest(),
                            "issues": [{"code": "unsupported_comparative_claim", "severity": "warning", "message": "Old unsupported claim."}],
                        }
                    ),
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_validation_json = str(validation_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                path, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
                self.assertTrue(path.exists())
                self.assertEqual(quality_eval["schema_version"], "quality-eval/1")
                tiers = quality_eval["tiers"]
                self.assertEqual(tiers["tier_0_preconditions"]["status"], "fail")
                self.assertIn("validation_report_stale", tiers["tier_0_preconditions"]["failing_codes"])
                self.assertEqual(tiers["tier_1_structural"]["status"], "skipped_due_to_upstream_fail")
                self.assertEqual(tiers["tier_2_claim_safety"]["status"], "skipped_due_to_upstream_fail")
                self.assertEqual(tiers["tier_3_scholarly_quality"]["status"], "skipped_due_to_upstream_fail")
                self.assertFalse((root / ".paper-orchestra" / "qa-loop-history.jsonl").exists())
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_loop_plan_v2_uses_safe_verdict_and_semi_auto_claim_repairs(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson and Sean Turner},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nIntro cites~\\cite{RFC9001}.\n"
                    "This draft is better than the baseline without a grounded log sentence.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 1,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
                            "issues": [
                                {
                                    "code": "unsupported_comparative_claim",
                                    "severity": "warning",
                                    "message": "Manuscript contains comparative claims not evidenced in the experimental log: better than",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_validation_json = str(validation_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")
                self.assertEqual(plan["schema_version"], "qa-loop-plan/2")
                self.assertIn(plan["verdict"], {"continue", "human_needed", "ready_for_human_finalization", "failed"})
                self.assertNotEqual(plan["verdict"], "success")
                self.assertIn("ready_for_human_finalization", plan["stop_conditions"])
                self.assertNotIn("success", plan["stop_conditions"])
                claim_actions = [action for action in plan["repair_actions"] if action["code"] == "unsupported_comparative_claim"]
                self.assertEqual(len(claim_actions), 1)
                self.assertEqual(claim_actions[0]["automation"], "semi_auto")
                self.assertIn("why_not_automatic", claim_actions[0])
                self.assertEqual(claim_actions[0]["approval_required_from"], "citation_support_critic")
                self.assertFalse(plan["quality_eval_summary"]["writer_score_visibility"]["writer_receives_scores"])
                history_path = root / ".paper-orchestra" / "qa-loop-history.jsonl"
                self.assertTrue(history_path.exists())
                last = json.loads(history_path.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(last["event_type"], "qa_loop_plan")
                self.assertFalse(last["consumes_budget"])
                self.assertIn("unsupported_comparative_claim", last["failing_codes"])
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_fidelity_parallel_evidence_survives_note_archival(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            state.notes = []
            state.notes_archive = ["Plot and literature completed in parallel."]
            save_session(root, state)

            payload = run_fidelity_audit(root)
            parallel_check = next(check for check in payload["checks"] if check["code"] == "parallel_step_2_3_semantics")
            self.assertEqual(parallel_check["status"], "implemented")

    def test_quality_loop_plan_rejects_stale_quality_eval_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nCurrent.\\end{document}\n",
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            state.latest_provider_name = "shell"
            save_session(root, state)
            stale_eval = artifact_path(root, "stale-quality-eval.json")
            stale_eval.write_text(
                json.dumps(
                    {
                        "schema_version": "quality-eval/1",
                        "manuscript_hash": "sha256:not-current",
                        "mode": "claim_safe",
                        "audit_snapshot_hashes": {},
                        "tiers": {
                            "tier_0_preconditions": {"status": "pass", "checks": {}, "failing_codes": []},
                            "tier_1_structural": {"status": "pass", "checks": {}, "failing_codes": []},
                            "tier_2_claim_safety": {"status": "pass", "checks": {}, "failing_codes": []},
                            "tier_3_scholarly_quality": {"status": "pass", "checks": {}, "failing_codes": [], "overall_score": 100, "axis_scores": {}},
                            "tier_4_human_finalization": {"status": "never_automated"},
                        },
                        "provenance_trust": {"level": "live"},
                        "cross_iteration": {"budget": {"remaining": 10}, "regression": {"forward_progress": True, "oscillation": {"detected": False}}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "quality-eval input is stale for the current manuscript"):
                write_quality_loop_plan(root, quality_eval_input_path=stale_eval)

    def _write_claim_safe_scaffolding(self, root: Path, paper_text: str) -> Path:
        seed_path = root / "claim-safe-refs.bib"
        seed_path.write_text(
            "@article{TestRef,\n"
            "  title = {Test Reference Paper},\n"
            "  author = {Ada Lovelace},\n"
            "  year = {2020},\n"
            "  url = {https://example.test/reference}\n"
            "}\n",
            encoding="utf-8",
        )
        import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
        if "\\cite" not in paper_text:
            paper_text = paper_text.replace(
                "\\end{document}",
                "Background context is documented~\\cite{TestRef}.\\end{document}",
            )
        paper_path = artifact_path(root, "paper.full.tex")
        paper_path.write_text(paper_text, encoding="utf-8")
        paper_path.with_suffix(".bbl").write_text(
            "\\begin{thebibliography}{1}\n"
            "\\bibitem{TestRef} Ada Lovelace. Test Reference Paper. 2020.\n"
            "\\end{thebibliography}\n",
            encoding="utf-8",
        )
        state = load_session(root)
        state.artifacts.paper_full_tex = str(paper_path)
        state.latest_provider_name = "shell"
        state.latest_runtime_mode = "compatibility"
        outline_path = artifact_path(root, "outline.json")
        outline_path.write_text(
            json.dumps(
                {
                    "plotting_plan": [],
                    "intro_related_work_plan": {},
                    "section_plan": [
                        {"section_title": "Introduction", "subsections": []},
                        {"section_title": "Related Work", "subsections": []},
                        {"section_title": "Method", "subsections": []},
                        {"section_title": "Experiments", "subsections": []},
                        {"section_title": "Discussion", "subsections": []},
                    ],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.outline_json = str(outline_path)
        prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
        (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
        (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
        state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
        save_session(root, state)
        plan_narrative_and_claims(root, MockProvider())
        write_source_obligations(root)
        record_current_validation_report(root, name="validation.current.json")
        write_figure_placement_review(root)
        manuscript_sha = hashlib.sha256(paper_path.read_bytes()).hexdigest()
        pdf_path = artifact_path(root, "paper.full.pdf")
        pdf_path.write_bytes(b"%PDF-1.4\n% synthetic test pdf\n")
        pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        compile_report = artifact_path(root, "compile-report.json")
        compile_report.write_text(
            json.dumps(
                {
                    "pdf_path": str(pdf_path),
                    "log_path": str(artifact_path(root, "latex-build.log")),
                    "source_path": str(paper_path),
                    "manuscript_sha256": manuscript_sha,
                    "pdf_sha256": pdf_sha,
                    "return_code": 0,
                    "pdf_exists": True,
                    "clean": True,
                    "warning_summary": [],
                }
            ),
            encoding="utf-8",
        )
        state = load_session(root)
        citation_map_sha = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
        citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
        provider = get_citation_support_provider("shell", evidence_mode="web")
        provider_digest = hashlib.sha256(json.dumps(provider.argv, ensure_ascii=False).encode("utf-8")).hexdigest()
        citation_support = paper_path.parent / "citation_support_review.json"
        items = [
            {
                "id": "cite-001",
                "sentence": "Background context is documented~\\cite{TestRef}.",
                "citation_keys": ["TestRef"],
                "citation_entries": [dict(citation_map["TestRef"], key="TestRef")],
                "support_status": "supported",
                "risk": "low",
                "claim_type": "background",
                "evidence": [
                    {
                        "citation_key": "TestRef",
                        "source_title": "Test Reference Paper",
                        "url": "https://example.test/reference",
                        "evidence_quote_or_summary": "The cited source provides the background context used in the sentence.",
                        "supports_claim": True,
                    }
                ],
            }
        ]
        trace = artifact_path(root, "citation-support-trace.json")
        trace.write_text(
            json.dumps(
                {
                    "schema_version": "citation-support-trace/1",
                    "manuscript_sha256": manuscript_sha,
                    "citation_map_sha256": citation_map_sha,
                    "review_mode": "web",
                    "web_search_required": True,
                    "web_search_capable": True,
                    "provider_command_digest": provider_digest,
                    "review_items_sha256": hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                    "system_prompt_sha256": "sha256-system",
                    "user_prompt_sha256": "sha256-user",
                    "response_sha256": "sha256-response",
                }
            ),
            encoding="utf-8",
        )
        citation_support.write_text(
            json.dumps(
                {
                    "schema_version": "citation-support-review/2",
                    "manuscript_sha256": manuscript_sha,
                    "citation_map_sha256": citation_map_sha,
                    "claims_checked": 1,
                    "items": items,
                    "summary": {"supported": 1},
                    "review_mode": "web",
                    "evidence_provenance": {
                        "mode": "web",
                        "claim_support_not_metadata_lookup": True,
                        "web_search_required": True,
                        "web_search_capable": True,
                        "provider_command_digest": provider_digest,
                        "model_review_used": True,
                        "review_trace_path": str(trace),
                        "review_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        review = artifact_path(root, "review.latest.json")
        axis_scores = {
            key: {"score": 86, "justification": "The manuscript includes explicit evidence in this axis."}
            for key in [
                "coverage_and_completeness",
                "relevance_and_focus",
                "critical_analysis_and_synthesis",
                "positioning_and_novelty",
                "organization_and_writing",
                "citation_practices_and_rigor",
            ]
        }
        review.write_text(
            json.dumps(
                {
                    "schema_version": "paper-review/1",
                    "paper_title": "Synthetic Test Paper",
                    "manuscript_path": str(paper_path),
                    "manuscript_sha256": manuscript_sha,
                    "citation_statistics": {},
                    "overall_score": 86,
                    "axis_scores": axis_scores,
                    "penalties": [],
                    "summary": {"strengths": [], "weaknesses": [], "top_improvements": []},
                    "questions": [],
                }
            ),
            encoding="utf-8",
        )
        state = load_session(root)
        state.artifacts.latest_compile_report_json = str(compile_report)
        state.artifacts.latest_review_json = str(review)
        save_session(root, state)
        _, rendered_reference_audit = write_rendered_reference_audit(root, quality_mode="claim_safe")
        _, citation_integrity_audit = write_citation_integrity_audit(root, quality_mode="claim_safe")
        critic_path = artifact_path(root, "citation_integrity.critic.json")
        critic_path.write_text(
            json.dumps(
                {
                    "schema_version": "citation-integrity-critic/1",
                    "status": "pass",
                    "manuscript_sha256": manuscript_sha,
                    "paper_full_tex_sha256": manuscript_sha,
                    "reviewed_artifacts": {
                        "rendered_reference_audit": {
                            "path": str(artifact_path(root, "rendered_reference_audit.json")),
                            "sha256": hashlib.sha256(
                                json.dumps(rendered_reference_audit, sort_keys=True, ensure_ascii=False).encode("utf-8")
                            ).hexdigest(),
                        },
                        "citation_integrity_audit": {
                            "path": str(artifact_path(root, "citation_integrity.audit.json")),
                            "sha256": hashlib.sha256(
                                json.dumps(citation_integrity_audit, sort_keys=True, ensure_ascii=False).encode("utf-8")
                            ).hexdigest(),
                        },
                    },
                    "failing_codes": [],
                }
            ),
            encoding="utf-8",
        )
        handoff_path = artifact_path(root, "ralph-handoff.json")
        handoff_path.write_text(
            json.dumps(
                {
                    "schema_version": "paperorchestra-ralph-handoff/1",
                    "session_id": state.session_id,
                    "execution_contract": {
                        "ralph_required": True,
                        "critic_required": True,
                        "citation_integrity_gate_required": True,
                        "human_needed_cycle_policy": {"requested_cycles": 5, "observed_cycles": 5},
                    },
                }
            ),
            encoding="utf-8",
        )
        (runtime_root(root) / "qa-loop-history.jsonl").write_text(
            json.dumps(
                {
                    "session_id": state.session_id,
                    "event_type": "qa_loop_step",
                    "consumes_budget": True,
                    "human_needed_cycles": 5,
                    "failing_codes": [],
                    "manuscript_hash": f"sha256:{manuscript_sha}",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return paper_path

    def test_quality_eval_sources_include_citation_intent_and_source_match_but_still_require_critic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\\begin{document}"
                "\\section{Introduction}Background context is documented~\\cite{TestRef}."
                "\\section{Related Work}Prior work motivates the fixture."
                "\\section{Method}The method is described."
                "\\section{Experiments}The experiment is synthetic."
                "\\section{Discussion}The discussion covers limits."
                "\\end{document}",
            )
            citation_integrity_critic_path(root).unlink()

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            source_artifacts = quality_eval["source_artifacts"]
            self.assertEqual(source_artifacts["citation_intent_plan"], str(citation_intent_plan_path(root)))
            self.assertTrue(source_artifacts["citation_intent_plan_sha256"])
            self.assertEqual(source_artifacts["citation_source_match"], str(citation_source_match_path(root)))
            self.assertTrue(source_artifacts["citation_source_match_sha256"])
            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertEqual(tier2["status"], "fail")
            self.assertIn("citation_critic_missing", tier2["failing_codes"])

    def _write_clean_compile_report_for_current(self, root: Path) -> None:
        state = load_session(root)
        paper_path = Path(state.artifacts.paper_full_tex)
        manuscript_sha = hashlib.sha256(paper_path.read_bytes()).hexdigest()
        pdf_path = artifact_path(root, "paper.full.pdf")
        pdf_path.write_bytes(b"%PDF-1.4\n% synthetic test pdf\n")
        pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        compile_report = artifact_path(root, "compile-report.json")
        compile_report.write_text(
            json.dumps(
                {
                    "pdf_path": str(pdf_path),
                    "log_path": str(artifact_path(root, "latex-build.log")),
                    "source_path": str(paper_path),
                    "manuscript_sha256": manuscript_sha,
                    "pdf_sha256": pdf_sha,
                    "return_code": 0,
                    "pdf_exists": True,
                    "clean": True,
                    "warning_summary": [],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.latest_compile_report_json = str(compile_report)
        save_session(root, state)

    def _valid_review_axes(self, score: int = 86) -> dict[str, dict[str, object]]:
        return {
            key: {"score": score, "justification": f"{key} is supported by concrete manuscript evidence in this fixture."}
            for key in [
                "coverage_and_completeness",
                "relevance_and_focus",
                "critical_analysis_and_synthesis",
                "positioning_and_novelty",
                "organization_and_writing",
                "citation_practices_and_rigor",
            ]
        }

    def _write_authenticated_review(self, root: Path, *, reviewer_label: str, review_name: str = "review.latest.json") -> Path:
        state = load_session(root)
        paper_path = Path(state.artifacts.paper_full_tex)
        manuscript_sha = hashlib.sha256(paper_path.read_bytes()).hexdigest()
        prompt_dir = artifact_path(root, "prompts/review.fixture.system.md").parent
        prompt_dir.mkdir(parents=True, exist_ok=True)
        provider_identity = artifact_path(root, f"provider-identity.{reviewer_label}.json")
        provider_identity.write_text(
            json.dumps(
                {
                    "provider_name": "fixture-reviewer",
                    "runtime_mode": "omx_native",
                    "stage": "review",
                    "provider_command_digest": reviewer_label,
                }
            ),
            encoding="utf-8",
        )
        meta_path = prompt_dir / f"review.{reviewer_label}.meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "stage": "review",
                    "provider_identity": {
                        "provider_name": "fixture-reviewer",
                        "runtime_mode": "omx_native",
                        "stage": "review",
                        "provider_command_digest": reviewer_label,
                    },
                }
            ),
            encoding="utf-8",
        )
        lane_path = record_lane_manifest(
            root,
            stage=f"review-{reviewer_label}",
            role="Reviewer Lane",
            runtime_mode="omx_native",
            lane_type="reviewer",
            owner="reviewer",
            status="completed",
            input_artifacts=[str(paper_path)],
            output_artifacts=[],
        )
        review = artifact_path(root, review_name) if "/" in review_name else root / ".paper-orchestra" / "runs" / state.session_id / "reviews" / review_name
        review.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "paper-review/1",
            "paper_title": "Authenticated Review Fixture",
            "manuscript_path": str(paper_path),
            "manuscript_sha256": manuscript_sha,
            "citation_statistics": {"notes": "fixture"},
            "overall_score": 86,
            "axis_scores": self._valid_review_axes(),
            "penalties": [],
            "summary": {
                "strengths": ["Grounded fixture."],
                "weaknesses": ["Still requires human finalization."],
                "top_improvements": ["Check final figures and venue fit."],
            },
            "questions": [],
            "review_provenance": {
                "schema_version": "review-provenance/1",
                "stage": "review",
                "manuscript_sha256": manuscript_sha,
                "reviewer_label": reviewer_label,
                "prompt_trace_meta_path": str(meta_path),
                "prompt_trace_meta_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
                "provider_identity_path": str(provider_identity),
                "provider_identity_sha256": hashlib.sha256(provider_identity.read_bytes()).hexdigest(),
                "provider_name": "fixture-reviewer",
                "provider_command_digest": reviewer_label,
                "runtime_mode": "omx_native",
                "lane_manifest_path": str(lane_path),
                "lane_manifest_sha256": hashlib.sha256(lane_path.read_bytes()).hexdigest(),
            },
        }
        review.write_text(json.dumps(payload), encoding="utf-8")
        state = load_session(root)
        state.artifacts.latest_review_json = str(review)
        state.review_history.append(ScoreSnapshot(overall_score=86, raw_path=str(review), axes={key: 86.0 for key in payload["axis_scores"]}))
        state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
        state.artifacts.latest_provider_identity_json = str(provider_identity)
        save_session(root, state)
        return review

    def _write_passing_section_review_for_current(self, root: Path) -> None:
        state = load_session(root)
        paper_path = Path(state.artifacts.paper_full_tex)
        review = paper_path.parent / "section_review.json"
        review.write_text(
            json.dumps(
                {
                    "schema_version": "section-review/1",
                    "manuscript_path": str(paper_path),
                    "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                    "overall_section_score": 86,
                    "sections": [
                        {"section_title": "Introduction", "score": 86, "verdict": "pass", "required_fixes": []}
                    ],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.latest_section_review_json = str(review)
        save_session(root, state)

    def test_quality_eval_claim_safe_rejects_review_without_provenance_even_with_high_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier3 = quality_eval["tiers"]["tier_3_scholarly_quality"]
            self.assertIn("review_provenance_missing", tier3["failing_codes"])
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")

    def test_quality_eval_claim_safe_rejects_review_with_missing_required_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            review_path = self._write_authenticated_review(root, reviewer_label="reviewer-a")
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            payload["axis_scores"].pop("positioning_and_novelty")
            review_path.write_text(json.dumps(payload), encoding="utf-8")

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier3 = quality_eval["tiers"]["tier_3_scholarly_quality"]
            self.assertIn("review_axes_incomplete", tier3["failing_codes"])

    def test_quality_eval_claim_safe_single_review_requires_independence_or_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            self._write_authenticated_review(root, reviewer_label="reviewer-a")

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier3 = quality_eval["tiers"]["tier_3_scholarly_quality"]
            self.assertIn("reviewer_independence_missing", tier3["failing_codes"])
            self.assertEqual(plan["verdict"], "human_needed")

    def test_quality_eval_claim_safe_two_distinct_reviewers_satisfy_independence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            self._write_authenticated_review(root, reviewer_label="reviewer-a", review_name="review.a.json")
            self._write_authenticated_review(root, reviewer_label="reviewer-b", review_name="review.b.json")

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            independence = quality_eval["tiers"]["tier_3_scholarly_quality"]["checks"]["reviewer_independence"]
            self.assertEqual(independence["status"], "pass")
            self.assertEqual(independence["distinct_reviewer_count"], 2)

    def test_reviewer_independence_ignores_unauthenticated_historical_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            self._write_authenticated_review(root, reviewer_label="reviewer-a")
            state = load_session(root)
            forged = artifact_path(root, "forged-review.json")
            forged.write_text(
                json.dumps(
                    {
                        "schema_version": "paper-review/1",
                        "manuscript_sha256": hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest(),
                        "overall_score": 99,
                        "axis_scores": self._valid_review_axes(99),
                        "penalties": [],
                        "summary": {"strengths": ["x"], "weaknesses": ["x"], "top_improvements": ["x"]},
                        "questions": [],
                        "review_provenance": {
                            "schema_version": "review-provenance/1",
                            "stage": "review",
                            "manuscript_sha256": hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest(),
                            "reviewer_label": "forged-reviewer",
                            "prompt_trace_meta_path": str(root / "missing-meta.json"),
                            "prompt_trace_meta_sha256": "0" * 64,
                            "provider_identity_path": str(root / "missing-provider.json"),
                            "provider_identity_sha256": "1" * 64,
                            "lane_manifest_path": str(root / "missing-lane.json"),
                            "lane_manifest_sha256": "2" * 64,
                        },
                    }
                ),
                encoding="utf-8",
            )
            state.review_history.append(ScoreSnapshot(overall_score=99, raw_path=str(forged), axes={}))
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            independence = quality_eval["tiers"]["tier_3_scholarly_quality"]["checks"]["reviewer_independence"]
            self.assertEqual(independence["status"], "fail")
            self.assertEqual(independence["distinct_reviewer_count"], 1)

    def test_reviewer_independence_acceptance_requires_writer_refiner_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            review_path = self._write_authenticated_review(root, reviewer_label="reviewer-a")
            state = load_session(root)
            acceptance = root / ".paper-orchestra" / "reviewer-independence-acceptance.json"
            acceptance.write_text(
                json.dumps(
                    {
                        "schema_version": "reviewer-independence-acceptance/1",
                        "manuscript_sha256": hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest(),
                        "review_artifacts": [{"path": str(review_path), "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest()}],
                        "rationale": "Operator accepts the single-review risk for this fixture.",
                        "operator_label": "tester",
                        "accepted_at": "2026-04-23T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            acceptance_check = quality_eval["tiers"]["tier_3_scholarly_quality"]["checks"]["reviewer_independence"]["acceptance"]
            self.assertIn("reviewer_independence_acceptance_incomplete", acceptance_check["failing_codes"])

    def test_codex_operator_feedback_cannot_satisfy_reviewer_independence_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            self._write_passing_section_review_for_current(root)
            review_path = self._write_authenticated_review(root, reviewer_label="reviewer-a")
            state = load_session(root)
            writer_refiner = root / "writer-refiner.json"
            writer_refiner.write_text('{"ok": true}', encoding="utf-8")
            acceptance = root / ".paper-orchestra" / "reviewer-independence-acceptance.json"
            acceptance.write_text(
                json.dumps(
                    {
                        "schema_version": "reviewer-independence-acceptance/1",
                        "source": "codex_operator",
                        "not_independent_human_review": True,
                        "manuscript_sha256": hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest(),
                        "review_artifacts": [{"path": str(review_path), "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest()}],
                        "rationale": "Codex operator feedback may guide rewriting but must not count as independent human review.",
                        "operator_label": "codex-operator",
                        "accepted_at": "2026-04-23T00:00:00Z",
                        "writer_refiner_provenance": [{"path": str(writer_refiner), "sha256": hashlib.sha256(writer_refiner.read_bytes()).hexdigest()}],
                    }
                ),
                encoding="utf-8",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            independence = quality_eval["tiers"]["tier_3_scholarly_quality"]["checks"]["reviewer_independence"]
            self.assertEqual(independence["status"], "fail")
            self.assertIn(
                "reviewer_independence_acceptance_operator_not_independent",
                independence["acceptance"]["failing_codes"],
            )

    def test_quality_eval_claim_safe_fails_when_source_obligations_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            state = load_session(root)
            path = Path(state.artifacts.source_obligations_json)
            path.unlink()
            state.artifacts.source_obligations_json = None
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertIn("source_obligations_missing", tier2["failing_codes"])

    def test_quality_eval_claim_safe_rejects_stale_source_obligation_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )
            state = load_session(root)
            obligations_path = Path(state.artifacts.source_obligations_json)
            payload = json.loads(obligations_path.read_text(encoding="utf-8"))
            payload["source_packet_sha256"] = "stale"
            obligations_path.write_text(json.dumps(payload), encoding="utf-8")

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertIn("source_obligations_stale", tier2["failing_codes"])

    def test_build_source_obligations_extracts_generic_material_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            Path(state.inputs.idea_path).write_text(
                "MethodX uses streaming-mode encryption with independently replaceable authentication under a hidden-state precondition.\n"
                "The theorem states invariant-safety and tamper-detection analysis bounds with Game 0, Game 1, and tag guessing steps.\n"
                "Limitations: the proof does not cover unavailable input exposure.\n",
                encoding="utf-8",
            )
            Path(state.inputs.experimental_log_path).write_text(
                "BenchHarness stq2 measurements compare Baseline-X throughput and show 2.54x at 16 bytes on the OpenSSL-backed implementation.\n",
                encoding="utf-8",
            )

            payload = build_source_obligations(root)

            types = {item["type"] for item in payload["obligations"]}
            self.assertTrue(
                {
                    "method_core",
                    "assumption_or_setup",
                    "theorem_or_bound",
                    "proof_step",
                    "benchmark_setup",
                    "benchmark_result",
                    "limitation_or_scope",
                }.issubset(types)
            )

    def test_generic_source_obligations_ignore_heading_only_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)

            payload = build_source_obligations(root)

            self.assertEqual(payload["obligations"], [])

    def test_generic_source_obligations_use_domain_neutral_material_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            Path(state.inputs.idea_path).write_text(
                "The method pipeline converts input artifacts into an outline and validates invariants before writing.\n"
                "The analysis proves a routing guarantee under the stated invariant assumptions.\n",
                encoding="utf-8",
            )
            Path(state.inputs.experimental_log_path).write_text(
                "Evaluation measurements report 12.7 ms latency and 4.2 jobs/s throughput on the demo workload.\n",
                encoding="utf-8",
            )

            payload = build_source_obligations(root)

            rendered = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("Baseline-X", rendered)
            self.assertNotIn("invariant-safety", rendered)
            self.assertNotIn("BenchHarness", rendered)
            types = {item["type"] for item in payload["obligations"]}
            self.assertIn("method_core", types)
            self.assertIn("theorem_or_bound", types)
            self.assertIn("benchmark_result", types)

    def test_quality_eval_claim_safe_routes_uncited_numeric_security_claim_to_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "Our scheme is 2.54x faster than Baseline-X and provides stronger security. "
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertIn("high_risk_uncited_claim", tier2["failing_codes"])
            self.assertEqual(plan["verdict"], "continue")
            high_risk_actions = [
                action for action in plan["repair_actions"] if action.get("code") == "high_risk_uncited_claim"
            ]
            self.assertEqual(len(high_risk_actions), 1)
            self.assertEqual(high_risk_actions[0]["automation"], "semi_auto")
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")

    def test_high_risk_claim_requires_specific_source_obligation_linkage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            Path(state.inputs.idea_path).write_text(
                "MethodX uses streaming-mode encryption with independently replaceable authentication under a hidden-state precondition.\n",
                encoding="utf-8",
            )
            Path(state.inputs.experimental_log_path).write_text(
                "BenchHarness stq2 measurements compare Baseline-X throughput and show 2.54x at 16 bytes.\n",
                encoding="utf-8",
            )
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "The MethodX authentication method is faster than Baseline-X. "
                "Background context is documented~\\cite{TestRef}.\n\\end{document}\n",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertIn("high_risk_uncited_claim", tier2["failing_codes"])

    def test_quality_eval_requires_current_compile_report_for_claim_safe_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            paper_path = self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "This is a structured but compile-untested manuscript.\n\\end{document}\n",
            )
            state = load_session(root)
            state.artifacts.latest_compile_report_json = None
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier1 = quality_eval["tiers"]["tier_1_structural"]
            self.assertEqual(tier1["status"], "fail")
            self.assertIn("compile_report_missing", tier1["failing_codes"])
            self.assertEqual(tier1["checks"]["compile_clean"]["expected_manuscript_sha256"], hashlib.sha256(paper_path.read_bytes()).hexdigest())

    def test_quality_eval_blocks_stale_clean_compile_report_for_changed_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            paper_path = self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nOriginal.\n\\end{document}\n",
            )
            paper_path.write_text(
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nChanged after compile.\n\\end{document}\n",
                encoding="utf-8",
            )
            record_current_validation_report(root, name="validation.current.json")
            write_figure_placement_review(root)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")

            tier1 = quality_eval["tiers"]["tier_1_structural"]
            self.assertEqual(tier1["status"], "fail")
            self.assertIn("compile_report_stale", tier1["failing_codes"])

    def test_quality_eval_blocks_high_review_score_without_section_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\n"
                "A polished but unsection-reviewed manuscript.\n\\end{document}\n",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier3 = quality_eval["tiers"]["tier_3_scholarly_quality"]
            self.assertEqual(tier3["status"], "warn")
            self.assertIn("section_review_missing", tier3["failing_codes"])
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")
            self.assertIn("section_review_missing", [action["code"] for action in plan["repair_actions"]])

    def test_quality_eval_blocks_paper_shaped_lorem_with_high_review_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            paper_path = self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nThin overview.\n"
                "\\section{Related Work}\nThin related work.\n"
                "\\section{Method}\nThin method.\n"
                "\\section{Experiments}\nThin experiment text.\n"
                "\\section{Conclusion}\nThin conclusion.\n"
                "\\end{document}\n",
            )
            low_section_review = paper_path.parent / "section_review.json"
            low_section_review.write_text(
                json.dumps(
                    {
                        "schema_version": "section-review/1",
                        "manuscript_path": str(paper_path),
                        "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                        "overall_section_score": 35,
                        "sections": [
                            {
                                "section_title": "Method",
                                "score": 25,
                                "verdict": "major_revision",
                                "required_fixes": ["Expand this section beyond a placeholder-level stub before relying on the critic score."],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            state = load_session(root)
            state.artifacts.latest_section_review_json = str(low_section_review)
            save_session(root, state)

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier3 = quality_eval["tiers"]["tier_3_scholarly_quality"]
            self.assertIn("section_quality_below_threshold", tier3["failing_codes"])
            self.assertNotEqual(plan["verdict"], "ready_for_human_finalization")
            self.assertIn("section_quality_below_threshold", [action["code"] for action in plan["repair_actions"]])

    def test_quality_eval_blocks_source_material_omission_even_when_reviewer_scores_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            state = load_session(root)
            Path(state.inputs.template_path).write_text(
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Security Analysis}\n"
                "\\begin{theorem}MethodX is invariant-safety secure under the hidden-state precondition.\\end{theorem}\n"
                "\\begin{proof}Game 0 is real. Game 1 replaces the stream. The analysis bound follows.\\end{proof}\n"
                "\\section{Experiments}\nBenchmark evidence.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            Path(state.inputs.experimental_log_path).write_text(
                "# Benchmark Method\nBenchHarness benchmark measurements show Baseline-X comparison result 2.54x at 16 bytes.\n",
                encoding="utf-8",
            )
            self._write_claim_safe_scaffolding(
                root,
                "\\documentclass{article}\n\\begin{document}\n"
                "\\section{Introduction}\nThe system discusses protected-channel design at a high level.\n"
                "\\section{Conclusion}\nThe work remains promising.\n"
                "\\end{document}\n",
            )

            _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
            _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")

            tier2 = quality_eval["tiers"]["tier_2_claim_safety"]
            self.assertEqual(tier2["status"], "fail")
            self.assertIn("source_material_proof_omitted", tier2["failing_codes"])
            self.assertIn("source_material_results_omitted", tier2["failing_codes"])
            self.assertEqual(quality_eval["tiers"]["tier_3_scholarly_quality"]["status"], "skipped_due_to_upstream_fail")
            self.assertIn("source_material_coverage_insufficient", [action["code"] for action in plan["repair_actions"]])

    def test_quality_loop_plan_requires_current_citation_support_review(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@article{RFC9001,\n"
                    "  title = {Using TLS to Secure QUIC},\n"
                    "  author = {Martin Thomson and Sean Turner},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nOriginal cites~\\cite{RFC9001}.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                citation_review_path = write_citation_support_review(root)
                fresh_payload = json.loads(Path(citation_review_path).read_text(encoding="utf-8"))
                self.assertEqual(fresh_payload["manuscript_sha256"], hashlib.sha256(paper_path.read_bytes()).hexdigest())

                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\nChanged claim cites~\\cite{RFC9001}.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 0,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "issues": [],
                        }
                    ),
                    encoding="utf-8",
                )
                state = load_session(root)
                state.artifacts.latest_validation_json = str(validation_path)
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                _, plan = write_quality_loop_plan(root, quality_mode="claim_safe")
                codes = [action["code"] for action in plan["repair_actions"]]
                self.assertIn("citation_support_review_stale", codes)
                self.assertIn("citation_support_review_stale", plan["quality_eval_summary"]["failing_codes"])
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_eval_tier2_fails_on_metadata_only_citation_support(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@techreport{RFC9001,\n"
                    "  title = {Using {TLS} to Secure {QUIC}},\n"
                    "  author = {Martin Thomson and Sean Turner},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\n"
                    "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 0,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "issues": [],
                        }
                    ),
                    encoding="utf-8",
                )
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.artifacts.latest_validation_json = str(validation_path)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                citation_review_path = write_citation_support_review(root)
                citation_review = json.loads(Path(citation_review_path).read_text(encoding="utf-8"))
                self.assertEqual(citation_review["summary"]["metadata_only"], 1)
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
                tier2 = quality_eval["tiers"]["tier_2_claim_safety"]

                self.assertEqual(tier2["status"], "fail")
                self.assertIn("citation_support_metadata_only", tier2["failing_codes"])
                self.assertEqual(
                    quality_eval["tiers"]["tier_3_scholarly_quality"]["status"],
                    "skipped_due_to_upstream_fail",
                )
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_eval_tier2_rejects_legacy_supported_citation_review(self) -> None:
        old_strict = os.environ.get("PAPERO_STRICT_CONTENT_GATES")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._init_session_with_minimal_inputs(root)
                seed_path = root / "refs.bib"
                seed_path.write_text(
                    "@techreport{RFC9001,\n"
                    "  title = {Using {TLS} to Secure {QUIC}},\n"
                    "  author = {Martin Thomson and Sean Turner},\n"
                    "  year = {2021}\n"
                    "}\n",
                    encoding="utf-8",
                )
                import_prior_work(root, seed_file=seed_path, source="manual_bibtex")
                paper_path = artifact_path(root, "paper.full.tex")
                paper_path.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\section{Introduction}\n"
                    "QUIC can use TLS for security~\\cite{RFC9001}.\n"
                    "\\end{document}\n",
                    encoding="utf-8",
                )
                prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
                (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
                (prompt_dir / "outline.user.md").write_text("user", encoding="utf-8")
                validation_path = artifact_path(root, "validation.sections.json")
                validation_path.write_text(
                    json.dumps(
                        {
                            "stage": "section_writing",
                            "ok": True,
                            "blocking_issue_count": 0,
                            "warning_count": 0,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "issues": [],
                        }
                    ),
                    encoding="utf-8",
                )
                state = load_session(root)
                state.artifacts.paper_full_tex = str(paper_path)
                state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
                state.artifacts.latest_validation_json = str(validation_path)
                state.latest_provider_name = "shell"
                state.latest_runtime_mode = "compatibility"
                save_session(root, state)
                write_figure_placement_review(root)
                plan_narrative_and_claims(root, MockProvider())
                self._write_clean_compile_report_for_current(root)
                legacy_path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
                expected_web_provider = get_citation_support_provider("shell", evidence_mode="web")
                self.assertIsInstance(expected_web_provider, ShellProvider)
                expected_web_digest = hashlib.sha256(
                    json.dumps(expected_web_provider.argv, ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                legacy_path.write_text(
                    json.dumps(
                        {
                            "session_id": state.session_id,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "claims_checked": 1,
                            "summary": {"supported": 1},
                            "items": [
                                {
                                    "id": "cite-001",
                                    "sentence": "QUIC can use TLS for security~\\cite{RFC9001}.",
                                    "citation_keys": ["RFC9001"],
                                    "support_status": "supported",
                                    "risk": "low",
                                    "evidence": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = "1"

                _, quality_eval = write_quality_eval(root, quality_mode="claim_safe")
                tier2 = quality_eval["tiers"]["tier_2_claim_safety"]

                self.assertEqual(tier2["status"], "fail")
                self.assertIn("citation_support_review_legacy_untrusted", tier2["failing_codes"])
                self.assertIn("citation_support_evidence_missing", tier2["failing_codes"])

                citation_map_sha = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
                legacy_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "citation-support-review/2",
                            "session_id": state.session_id,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "citation_map_sha256": citation_map_sha,
                            "review_mode": "model",
                            "evidence_provenance": {
                                "mode": "model",
                                "semantic_scholar_required": False,
                                "web_search_required": False,
                                "model_review_used": True,
                                "claim_support_not_metadata_lookup": True,
                            },
                            "claims_checked": 1,
                            "summary": {"verified": 1},
                            "items": [
                                {
                                    "id": "cite-001",
                                    "sentence": "QUIC can use TLS for security~\\cite{RFC9001}.",
                                    "citation_keys": ["RFC9001"],
                                    "support_status": "verified",
                                    "risk": "low",
                                    "evidence": [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

                _, invalid_status_eval = write_quality_eval(root, quality_mode="claim_safe")
                invalid_tier2 = invalid_status_eval["tiers"]["tier_2_claim_safety"]
                self.assertEqual(invalid_tier2["status"], "fail")
                self.assertIn("citation_support_invalid_status", invalid_tier2["failing_codes"])

                legacy_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "citation-support-review/2",
                            "session_id": state.session_id,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "citation_map_sha256": citation_map_sha,
                            "review_mode": "model",
                            "evidence_provenance": {
                                "mode": "model",
                                "semantic_scholar_required": False,
                                "web_search_required": False,
                                "model_review_used": True,
                                "claim_support_not_metadata_lookup": True,
                            },
                            "claims_checked": 1,
                            "summary": {"supported": 1},
                            "items": [
                                {
                                    "id": "cite-001",
                                    "sentence": "QUIC can use TLS for security~\\cite{RFC9001}.",
                                    "citation_keys": ["RFC9001"],
                                    "citation_entries": [
                                        {
                                            "key": "RFC9001",
                                            "title": "Using TLS to Secure QUIC",
                                            "url": "https://www.rfc-editor.org/rfc/rfc9001",
                                        }
                                    ],
                                    "support_status": "supported",
                                    "risk": "low",
                                    "evidence": [
                                        {
                                            "citation_key": "RFC9001",
                                            "source_title": "Hallucinated source",
                                            "url": "https://example.com/not-rfc9001",
                                            "evidence_quote_or_summary": "Trust me.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

                _, hallucinated_eval = write_quality_eval(root, quality_mode="claim_safe")
                hallucinated_tier2 = hallucinated_eval["tiers"]["tier_2_claim_safety"]
                self.assertEqual(hallucinated_tier2["status"], "fail")
                self.assertIn("citation_support_non_web_supported", hallucinated_tier2["failing_codes"])
                self.assertIn("citation_support_evidence_missing", hallucinated_tier2["failing_codes"])

                legacy_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "citation-support-review/2",
                            "session_id": state.session_id,
                            "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                            "citation_map_sha256": citation_map_sha,
                            "review_mode": "web",
                            "evidence_provenance": {
                                "mode": "web",
                                "semantic_scholar_required": False,
                                "web_search_required": True,
                                "web_search_capable": True,
                                "provider_command_digest": expected_web_digest,
                                "model_review_used": True,
                                "claim_support_not_metadata_lookup": True,
                            },
                            "claims_checked": 1,
                            "summary": {"supported": 1},
                            "items": [
                                {
                                    "id": "cite-001",
                                    "sentence": "QUIC can use TLS for security~\\cite{RFC9001}.",
                                    "citation_keys": ["RFC9001"],
                                    "support_status": "supported",
                                    "risk": "low",
                                    "evidence": [
                                        {
                                            "citation_key": "RFC9001",
                                            "source_title": "Using TLS to Secure QUIC",
                                            "url": "https://www.rfc-editor.org/rfc/rfc9001",
                                            "evidence_quote_or_summary": "The source describes using TLS to secure QUIC.",
                                            "supports_claim": True,
                                        }
                                    ],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

                _, forged_web_eval = write_quality_eval(root, quality_mode="claim_safe")
                forged_web_tier2 = forged_web_eval["tiers"]["tier_2_claim_safety"]
                self.assertEqual(forged_web_tier2["status"], "fail")
                self.assertIn("citation_support_trace_missing", forged_web_tier2["failing_codes"])

                forged_trace_path = legacy_path.with_name("citation_support_review.trace.json")
                forged_trace_text = json.dumps(
                    {
                        "schema_version": "citation-support-trace/1",
                        "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                        "citation_map_sha256": citation_map_sha,
                        "review_mode": "web",
                        "web_search_required": True,
                        "provider_command_digest": expected_web_digest,
                        "web_search_capable": True,
                        "system_prompt_sha256": "0" * 64,
                        "user_prompt_sha256": "1" * 64,
                        "response_sha256": "2" * 64,
                        "review_items_sha256": "3" * 64,
                    },
                    indent=2,
                ) + "\n"
                forged_trace_path.write_text(forged_trace_text, encoding="utf-8")
                forged_trace_sha = hashlib.sha256(forged_trace_text.encode("utf-8")).hexdigest()
                forged_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
                forged_payload["evidence_provenance"]["review_trace_path"] = str(forged_trace_path)
                forged_payload["evidence_provenance"]["review_trace_sha256"] = forged_trace_sha
                legacy_path.write_text(json.dumps(forged_payload), encoding="utf-8")

                _, forged_trace_eval = write_quality_eval(root, quality_mode="claim_safe")
                forged_trace_tier2 = forged_trace_eval["tiers"]["tier_2_claim_safety"]
                self.assertEqual(forged_trace_tier2["status"], "fail")
                self.assertIn("citation_support_trace_invalid", forged_trace_tier2["failing_codes"])
        finally:
            if old_strict is None:
                os.environ.pop("PAPERO_STRICT_CONTENT_GATES", None)
            else:
                os.environ["PAPERO_STRICT_CONTENT_GATES"] = old_strict

    def test_quality_loop_plan_quotes_section_names_in_suggested_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            paper_path = artifact_path(root, "paper.full.tex")
            paper_path.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Results}\nBody.\\end{document}\n", encoding="utf-8")
            review_path = artifact_path(root, "figure-placement-review.json")
            review_path.write_text(
                json.dumps(
                    {
                        "manuscript_sha256": hashlib.sha256(paper_path.read_bytes()).hexdigest(),
                        "figures": [
                            {
                                "label": "fig:bad",
                                "section_title": "Results; rm -rf /",
                                "warning_codes": ["tail_clump"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            prompt_dir = artifact_path(root, "prompts/dummy.system.md").parent
            (prompt_dir / "outline.system.md").write_text("system", encoding="utf-8")
            state = load_session(root)
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.latest_figure_placement_review_json = str(review_path)
            state.artifacts.latest_prompt_trace_dir = str(prompt_dir)
            state.latest_provider_name = "shell"
            save_session(root, state)

            _, plan = write_quality_loop_plan(root)
            figure_action = next(action for action in plan["repair_actions"] if action["code"] == "tail_clump")
            command = " ".join(figure_action["suggested_commands"])
            self.assertIn("'Results; rm -rf /'", command)
            self.assertNotIn('"Results; rm -rf /"', command)

    def test_session_archives_older_notes_after_retention_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            state.notes = [f"note-{idx}" for idx in range(25)]
            save_session(root, state)
            reloaded = load_session(root)
            self.assertEqual(len(reloaded.notes), 20)
            self.assertEqual(reloaded.notes_archive, [f"note-{idx}" for idx in range(5)])
