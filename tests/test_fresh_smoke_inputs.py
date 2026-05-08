from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from paperorchestra.literature import load_prior_work_seed


class FreshSmokeInputDerivationTests(unittest.TestCase):
    def test_citation_free_material_packet_still_derives_usable_prior_work_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(Path("examples/fresh-smoke-materials/materials"), root / "inputs-materials")
            shutil.copy2(Path("examples/fresh-smoke-materials/policy/material-boundary.md"), root / "inputs-materials" / "material-boundary.md")

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
