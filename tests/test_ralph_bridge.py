from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.models import InputBundle
from paperorchestra.ralph_bridge import build_qa_loop_brief, build_ralph_start_payload
from paperorchestra.ralph_bridge_state import _qa_loop_step_command
from paperorchestra.session import artifact_path, create_session, save_session


class RalphBridgeProviderSplitTests(unittest.TestCase):
    def _session(self, root: Path):
        for name, content in {
            "idea.md": "Demo",
            "experimental_log.md": "Log",
            "template.tex": "\\documentclass{article}\\begin{document}\\end{document}",
            "guidelines.md": "Guidelines",
        }.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "figures").mkdir()
        state = create_session(root, InputBundle(str(root/"idea.md"), str(root/"experimental_log.md"), str(root/"template.tex"), str(root/"guidelines.md"), str(root/"figures")))
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text("\\section{Intro}\nBody.\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        save_session(root, state)

    def test_qa_loop_step_command_and_payload_include_citation_provider(self) -> None:
        command = _qa_loop_step_command(quality_mode="claim_safe", max_iterations=5, require_live_verification=True, accept_mixed_provenance=False)
        self.assertIn("--provider-command \"$PAPERO_MODEL_CMD\"", command)
        self.assertIn("--citation-provider-command \"$PAPERO_WEB_PROVIDER_CMD\"", command)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._session(root)
            brief = build_qa_loop_brief(root, quality_mode="claim_safe", max_iterations=5, require_live_verification=True)
            self.assertIn("PAPERO_WEB_PROVIDER_CMD", brief)
            payload = build_ralph_start_payload(root, quality_mode="claim_safe", max_iterations=5, require_live_verification=True)
            self.assertIn("--citation-provider-command", payload["execution_contract"]["step_command"])
            self.assertTrue(payload["execution_contract"]["requires_papero_web_provider_cmd"])
