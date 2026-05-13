from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main
from paperorchestra.orchestra_evidence import write_orchestrator_evidence_bundle
from paperorchestra.orchestra_state import NextAction, OrchestraFacets, OrchestraState


@contextlib.contextmanager
def _chdir(path: str | Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class OrchestraEvidenceBundleTests(unittest.TestCase):
    def _state_with_private_surfaces(self, root: Path) -> OrchestraState:
        state = OrchestraState.new(
            cwd=root,
            facets=OrchestraFacets(material="inventoried_sufficient", source_digest="ready", writing="not_allowed"),
            next_actions=[NextAction("start_autoresearch", "research_needed")],
            private_notes=["PRIVATE_NOTE_SHOULD_NOT_LEAK"],
            author_override="PRIVATE_AUTHOR_OVERRIDE_SHOULD_REDACT",
        )
        state.evidence_refs = [
            {
                "kind": "synthetic_nested",
                "payload": {
                    "safe": "ok",
                    "workspace_path": str(root / "private" / "raw-material.txt"),
                    "nested": [
                        {"raw_text": "PRIVATE_RAW_TEXT_SHOULD_NOT_LEAK"},
                        {"private_marker": "PRIVATE_MARKER_SHOULD_NOT_LEAK"},
                        {"prompt": "PRIVATE_PROMPT_SHOULD_NOT_LEAK"},
                        {"argv": ["PRIVATE_ARG_SHOULD_NOT_LEAK"]},
                        {"executable_command": "PRIVATE_COMMAND_SHOULD_NOT_LEAK"},
                    ],
                },
            }
        ]
        return state

    def test_writes_state_evidence_and_manifest_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._state_with_private_surfaces(root)
            bundle = write_orchestrator_evidence_bundle(root, state)
            manifest_path = Path(bundle["manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], "orchestrator-evidence-bundle/1")
        self.assertEqual(manifest["evidence_count"], 1)
        self.assertEqual(len(manifest["state_sha256"]), 64)
        self.assertEqual(len(manifest["evidence"][0]["sha256"]), 64)
        self.assertEqual(manifest["state_path"], "orchestra-state.json")
        self.assertTrue(manifest["evidence"][0]["path"].startswith("evidence/"))

    def test_bundle_redacts_private_state_and_nested_evidence_payloads(self) -> None:
        markers = [
            "PRIVATE_NOTE_SHOULD_NOT_LEAK",
            "PRIVATE_AUTHOR_OVERRIDE_SHOULD_REDACT",
            "PRIVATE_RAW_TEXT_SHOULD_NOT_LEAK",
            "PRIVATE_MARKER_SHOULD_NOT_LEAK",
            "PRIVATE_PROMPT_SHOULD_NOT_LEAK",
            "PRIVATE_ARG_SHOULD_NOT_LEAK",
            "PRIVATE_COMMAND_SHOULD_NOT_LEAK",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = write_orchestrator_evidence_bundle(root, self._state_with_private_surfaces(root))
            output_dir = Path(bundle["output_dir"])
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))
            state_payload = json.loads((output_dir / "orchestra-state.json").read_text(encoding="utf-8"))

        for marker in markers:
            self.assertNotIn(marker, rendered)
        self.assertNotIn(str(root), rendered)
        self.assertIn('"author_override": "redacted"', rendered)
        self.assertIn('"raw_text": "<redacted>"', rendered)
        self.assertIs(state_payload["private_safe"], True)

    def test_output_outside_workspace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            outside = Path(tmp) / "outside"
            state = self._state_with_private_surfaces(root)
            with self.assertRaises(ValueError):
                write_orchestrator_evidence_bundle(root, state, output_dir=outside)

    def test_manifest_uses_relative_paths_and_omits_absolute_workspace_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = write_orchestrator_evidence_bundle(root, self._state_with_private_surfaces(root))
            manifest_text = Path(bundle["manifest_path"]).read_text(encoding="utf-8")

        self.assertNotIn(str(root), manifest_text)
        manifest = json.loads(manifest_text)
        self.assertEqual(manifest["manifest_path"], "manifest.json")
        self.assertFalse(Path(manifest["evidence"][0]["path"]).is_absolute())

    def test_cli_orchestrate_write_evidence_reports_manifest_path_without_drafting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text("We propose a new synthetic workflow.\n", encoding="utf-8")
            (material / "references.bib").write_text(
                "@article{synthetic2026,title={Synthetic Ref},author={Ada Example},year={2026}}\n",
                encoding="utf-8",
            )
            (material / "notes.md").write_text("Synthetic notes.\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--material", str(material), "--write-evidence", "--json"])
            payload = json.loads(stdout.getvalue())
            manifest_exists = Path(payload["evidence_bundle"]["manifest_path"]).exists()

        self.assertEqual(exit_code, 0)
        self.assertIn("evidence_bundle", payload)
        self.assertTrue(manifest_exists)
        self.assertNotEqual(payload["state"]["facets"]["writing"], "drafting_allowed")
        self.assertNotEqual(payload["state"]["readiness"]["label"], "ready_for_human_finalization")


if __name__ == "__main__":
    unittest.main()
