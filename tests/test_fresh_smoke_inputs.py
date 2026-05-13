from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from paperorchestra.literature import load_prior_work_seed
from paperorchestra.validator import check_prompt_meta_leakage


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

            entries = load_prior_work_seed(root / "workdir" / "inputs" / "reference_metadata_seed.bib", source="test_seed")
            self.assertEqual(entries, [])

    def test_mixed_known_and_unknown_citations_seed_only_known_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materials = self._write_citation_free_material_packet(root)
            method = materials / "01_methodology_core.tex"
            method.write_text(
                r"""
                \section{Method Core}
                Known background remains seedable~\cite{lewis2020retrievalaugmented},
                but private or placeholder keys without metadata must stay out of BibTeX~\cite{NotARealMetadataKey2024}.
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


if __name__ == "__main__":
    unittest.main()
