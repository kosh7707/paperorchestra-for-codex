from __future__ import annotations

import importlib
import unittest

from paperorchestra.cli import build_parser
from paperorchestra.mcp_server import TOOLS, TOOL_HANDLERS


class PublicSurfaceTest(unittest.TestCase):
    def test_cli_surface_is_small_and_explicit(self) -> None:
        parser = build_parser()
        commands = set()
        for action in parser._actions:
            if hasattr(action, "choices") and action.choices:
                commands = set(action.choices)
                break
        self.assertEqual(
            commands,
            {
                "answer-human-needed",
                "compile",
                "critique",
                "doctor",
                "environment",
                "export-current",
                "import-prior-work",
                "init",
                "inspect-state",
                "orchestrate",
                "qa-loop",
                "qa-loop-step",
                "quality-gate",
                "ralph-start",
                "research-prior-work",
                "run",
                "status",
                "write-sections",
            },
        )

    def test_mcp_surface_is_small_and_handler_backed(self) -> None:
        names = {tool["name"] for tool in TOOLS}
        self.assertEqual(
            names,
            {
                "answer_human_needed",
                "compile_current_paper",
                "critique",
                "export_current",
                "import_prior_work",
                "init_session",
                "inspect_state",
                "orchestrate",
                "qa_loop",
                "qa_loop_step",
                "quality_gate",
                "ralph_start",
                "research_prior_work",
                "run_pipeline",
                "status",
                "write_sections",
            },
        )
        self.assertEqual(names, set(TOOL_HANDLERS))

    def test_loop_engine_modules_import_from_new_packages(self) -> None:
        for module in (
            "paperorchestra.loop_engine.orchestra",
            "paperorchestra.loop_engine.quality.gate",
            "paperorchestra.loop_engine.quality.loop",
            "paperorchestra.loop_engine.ralph.bridge",
        ):
            with self.subTest(module=module):
                importlib.import_module(module)


if __name__ == "__main__":
    unittest.main()
