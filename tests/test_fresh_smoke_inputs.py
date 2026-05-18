from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from paperorchestra.literature import load_prior_work_seed
from paperorchestra.validator import check_prompt_meta_leakage, extract_citation_keys


class FreshSmokeInputDerivationTests(unittest.TestCase):
    def _write_citation_free_material_packet(self, root: Path) -> Path:
        materials = root / "inputs-materials"
        materials.mkdir()
        files = {
            "00_core_macros.tex": r"""
                % Generic test-only macro packet.
                % PaperOrchestra authoring note must not reach generated TeX.
                \newcommand{\SystemName}{\textsc{PaperFlow}}
                \newcommand{\PercentLiteral}{100\%}
                \newcommand{\InlineCommentPreserved}{value} % PaperOrchestra inline note is source-only.
            """,
            "01_methodology_core.tex": r"""
                \section{Method Core}
                The system records generated artifacts, validates them before promotion,
                and keeps author-facing review evidence with each candidate draft.
            """,
            "02_security_model_and_full_proof.tex": r"""
                \section{Validation Argument}
                Promotion is permitted only after independent checks confirm that
                candidate changes remain within the registered author evidence.
            """,
            "03_benchmark_method_and_results_core.tex": r"""
                \section{Evaluation Core}
                The benchmark records wall-clock cost, generated artifact count,
                and reviewer-visible failure reasons for each drafting stage.
            """,
            "04_claim_boundaries.tex": r"""
                The draft must not claim results beyond the registered evaluation log.
            """,
            "05_author_notes_for_positioning.tex": r"""
                Position the system as a conservative artifact-first writing assistant.
            """,
            "material-boundary.md": "Use only the registered test packet as paper-specific evidence.\n",
        }
        for name, content in files.items():
            (materials / name).write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
        return materials

    def _write_material_manifest(self, root: Path, entries: list[dict[str, object]]) -> None:
        evidence_only = root / "evidence-only"
        evidence_only.mkdir(exist_ok=True)
        (evidence_only / "material-manifest.original.json").write_text(
            json.dumps({"schema_version": "fresh-smoke-material-manifest/1", "materials": entries}, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def test_citation_free_material_packet_still_derives_usable_prior_work_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_citation_free_material_packet(root)

            subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                check=True,
                text=True,
                capture_output=True,
            )

            template = root / "workdir" / "inputs" / "template.tex"
            template_text = template.read_text(encoding="utf-8")
            self.assertIn(r"\newcommand{\SystemName}", template_text)
            self.assertIn(r"\newcommand{\PercentLiteral}{100\%}", template_text)
            self.assertIn(r"\newcommand{\InlineCommentPreserved}{value}", template_text)
            self.assertNotIn("Generic test-only macro packet", template_text)
            self.assertNotIn("PaperOrchestra authoring note", template_text)
            self.assertNotIn("PaperOrchestra inline note", template_text)
            self.assertIn(r"\title{Technical Research Study}", template_text)
            self.assertNotIn("Artifact-Governed Drafting with Promotion-Time Validation", template_text)
            self.assertNotIn("PaperOrchestra writes this", template_text)
            self.assertNotIn("Supplied Method", template_text)
            self.assertFalse(check_prompt_meta_leakage(template_text), template_text)

            seed = root / "workdir" / "inputs" / "reference_metadata_seed.bib"
            text = seed.read_text(encoding="utf-8")
            self.assertIn("Retrieval-Augmented Generation", text)
            self.assertIn("Self-Refine", text)
            self.assertIn("ReAct", text)

            entries = load_prior_work_seed(seed, source="test_seed")
            self.assertGreaterEqual(len(entries), 3)
            self.assertTrue(all(entry.get("title") for entry in entries))

    def test_material_heading_can_supply_non_meta_template_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            method = materials / "01_methodology_core.tex"
            method.write_text(
                r"""
                \title{Latency-Aware Storage Indexing}
                \section{Method Core}
                Registered test evidence describes an indexing method and its evaluation boundaries.
                """,
                encoding="utf-8",
            )

            subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                check=True,
                text=True,
                capture_output=True,
            )

            template_text = (root / "workdir" / "inputs" / "template.tex").read_text(encoding="utf-8")
            self.assertIn(r"\title{Latency-Aware Storage Indexing}", template_text)
            self.assertNotIn("Artifact-Governed Drafting with Promotion-Time Validation", template_text)
            self.assertFalse(check_prompt_meta_leakage(template_text), template_text)

            ledger = (root / "workdir" / "inputs" / "provenance-ledger.json").read_text(encoding="utf-8")
            self.assertIn("01_methodology_core.tex", ledger)

    def test_metadata_less_citation_keys_are_not_promoted_to_fake_bibtex_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            method = materials / "01_methodology_core.tex"
            method.write_text(
                r"""
                \section{Method Core}
                This source cites an author placeholder key that has no bundled metadata~\cite{NotARealMetadataKey2024}.
                """,
                encoding="utf-8",
            )

            subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                check=True,
                text=True,
                capture_output=True,
            )

            seed_text = (root / "workdir" / "inputs" / "reference_metadata_seed.bib").read_text(encoding="utf-8")
            self.assertNotIn("@misc{NotARealMetadataKey2024", seed_text)
            self.assertNotIn("Not A Real Metadata Key2024", seed_text)
            self.assertIn("Source citation keys without seed metadata: 1", seed_text)
            self.assertIn("Source citation command occurrences removed from prompt inputs: 1", seed_text)

            entries = load_prior_work_seed(root / "workdir" / "inputs" / "reference_metadata_seed.bib", source="test_seed")
            self.assertEqual(entries, [])
            idea = (root / "workdir" / "inputs" / "idea.tex").read_text(encoding="utf-8")
            self.assertEqual(extract_citation_keys(idea), set())
            self.assertNotIn("~.", idea)

    def test_mixed_known_and_unknown_citations_seed_only_known_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            method = materials / "01_methodology_core.tex"
            method.write_text(
                r"""
                \section{Method Core}
                Known background remains seedable~\cite{lewis2020retrievalaugmented},
                but private or placeholder keys without metadata must stay out of BibTeX~\citealp{NotARealMetadataKey2024}.
                """,
                encoding="utf-8",
            )

            subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                check=True,
                text=True,
                capture_output=True,
            )

            seed = root / "workdir" / "inputs" / "reference_metadata_seed.bib"
            seed_text = seed.read_text(encoding="utf-8")
            self.assertIn("@misc{lewis2020retrievalaugmented", seed_text)
            self.assertIn("Retrieval-Augmented Generation", seed_text)
            self.assertNotIn("@misc{NotARealMetadataKey2024", seed_text)
            self.assertIn("Source citation keys without seed metadata: 1", seed_text)

            entries = load_prior_work_seed(seed, source="test_seed")
            self.assertEqual([entry["bibtex_key"] for entry in entries], ["lewis2020retrievalaugmented"])
            idea = (root / "workdir" / "inputs" / "idea.tex").read_text(encoding="utf-8")
            self.assertEqual(extract_citation_keys(idea), {"lewis2020retrievalaugmented"})
            self.assertNotIn("NotARealMetadataKey2024", idea)
            ledger = json.loads((root / "workdir" / "inputs" / "provenance-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["source_citation_policy"]["unique_source_citation_keys"], 2)
            self.assertEqual(ledger["source_citation_policy"]["metadata_backed_prompt_citation_keys"], 1)
            self.assertEqual(ledger["source_citation_policy"]["metadata_less_source_citation_keys_removed"], 1)

    def test_registered_source_figures_are_generic_prompt_facing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            figures = materials / "figures"
            figures.mkdir()
            raw_name = "author_benchmark_internal_result.png"
            raw_bytes = b"\x89PNG\r\n\x1a\nregistered figure bytes\n"
            source = figures / raw_name
            source.write_bytes(raw_bytes)
            digest = hashlib.sha256(raw_bytes).hexdigest()
            self._write_material_manifest(
                root,
                [
                    {
                        "path": f"figures/{raw_name}",
                        "sha256": f"sha256:{digest}",
                        "bytes": len(raw_bytes),
                    }
                ],
            )

            subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                check=True,
                text=True,
                capture_output=True,
            )

            output = root / "workdir" / "inputs" / "figures" / "source-figure-001.png"
            self.assertEqual(output.read_bytes(), raw_bytes)
            figure_listing = "\n".join(path.name for path in (root / "workdir" / "inputs" / "figures").iterdir())
            self.assertIn("source-figure-001.png", figure_listing)
            self.assertNotIn(raw_name, figure_listing)

            ledger_text = (root / "workdir" / "inputs" / "provenance-ledger.json").read_text(encoding="utf-8")
            ledger = json.loads(ledger_text)
            figure_items = [item for item in ledger["items"] if item.get("role") == "source_figure_asset"]
            self.assertEqual(len(figure_items), 1)
            self.assertEqual(figure_items[0]["output"], "workdir/inputs/figures/source-figure-001.png")
            self.assertEqual(figure_items[0]["sha256"], digest)
            self.assertEqual(figure_items[0]["byte_size"], len(raw_bytes))
            self.assertEqual(figure_items[0]["extension"], ".png")
            self.assertIn("source_path_sha256", figure_items[0])
            self.assertNotIn(raw_name, ledger_text)

            for generated in [
                root / "workdir" / "inputs" / "idea.tex",
                root / "workdir" / "inputs" / "experimental_log.tex",
                root / "workdir" / "inputs" / "template.tex",
                root / "workdir" / "inputs" / "guidelines.md",
            ]:
                self.assertNotIn(raw_name, generated.read_text(encoding="utf-8"))

    def test_unregistered_source_figure_fails_closed_without_raw_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            figures = materials / "figures"
            figures.mkdir()
            raw_name = "author_benchmark_internal_result.png"
            (figures / raw_name).write_bytes(b"\x89PNG\r\n\x1a\nunregistered figure bytes\n")

            result = subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("unregistered_source_figure_asset", combined)
            self.assertNotIn(raw_name, combined)

    def test_registered_source_figure_missing_directory_fails_without_raw_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_citation_free_material_packet(root)
            raw_name = "author_benchmark_internal_result.png"
            self._write_material_manifest(
                root,
                [
                    {
                        "path": f"figures/{raw_name}",
                        "sha256": "sha256:" + "a" * 64,
                        "bytes": 12,
                    }
                ],
            )

            result = subprocess.run(
                ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("registered_source_figure_missing", combined)
            self.assertNotIn(raw_name, combined)

    def test_source_figure_manifest_metadata_failures_are_generic(self) -> None:
        cases = [
            ("missing_hash", {"bytes": 3}, "source_figure_hash_missing_or_invalid"),
            ("malformed_hash", {"sha256": "sha256:", "bytes": 3}, "source_figure_hash_missing_or_invalid"),
            ("missing_bytes", {"sha256": "sha256:" + "a" * 64}, "source_figure_size_missing_or_invalid"),
            ("string_bytes", {"sha256": "sha256:" + "a" * 64, "bytes": "3"}, "source_figure_size_missing_or_invalid"),
            ("hash_mismatch", {"sha256": "sha256:" + "b" * 64, "bytes": 3}, "source_figure_hash_mismatch"),
            (
                "size_mismatch",
                {"sha256": "sha256:" + hashlib.sha256(b"abc").hexdigest(), "bytes": 4},
                "source_figure_size_mismatch",
            ),
        ]
        for _label, metadata, expected_error in cases:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                materials = self._write_citation_free_material_packet(root)
                figures = materials / "figures"
                figures.mkdir()
                raw_name = "author_benchmark_internal_result.png"
                (figures / raw_name).write_bytes(b"abc")
                entry = {"path": f"figures/{raw_name}", **metadata}
                self._write_material_manifest(root, [entry])

                result = subprocess.run(
                    ["python3", "scripts/derive-fresh-smoke-inputs.py", str(root)],
                    text=True,
                    capture_output=True,
                )

                self.assertNotEqual(result.returncode, 0)
                combined = result.stdout + result.stderr
                self.assertIn(expected_error, combined)
                self.assertNotIn(raw_name, combined)


if __name__ == "__main__":
    unittest.main()
