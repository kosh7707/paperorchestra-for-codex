from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from paperorchestra.literature import load_prior_work_seed


class FreshSmokeInputDerivationTests(unittest.TestCase):
    def _write_citation_free_material_packet(self, root: Path) -> Path:
        materials = root / "inputs-materials"
        materials.mkdir()
        files = {
            "00_core_macros.tex": r"""
                % Generic test-only macro packet.
                \newcommand{\SystemName}{\textsc{PaperFlow}}
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
            self.assertIn("Artifact-Governed Drafting with Promotion-Time Validation", template_text)
            self.assertNotIn("Supplied Method", template_text)

            seed = root / "workdir" / "inputs" / "reference_metadata_seed.bib"
            text = seed.read_text(encoding="utf-8")
            self.assertIn("Retrieval-Augmented Generation", text)
            self.assertIn("Self-Refine", text)
            self.assertIn("ReAct", text)

            entries = load_prior_work_seed(seed, source="test_seed")
            self.assertGreaterEqual(len(entries), 3)
            self.assertTrue(all(entry.get("title") for entry in entries))


if __name__ == "__main__":
    unittest.main()
