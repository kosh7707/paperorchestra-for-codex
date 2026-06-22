from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path
import unittest

import paperorchestra
from paperorchestra.cli import build_parser
from paperorchestra.mcp_server import TOOLS, TOOL_HANDLERS
from paperorchestra.runtime.environment import package_context


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
                "approve-plan",
                "authoring-round",
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
                "visual-audit",
                "write-sections",
            },
        )

    def test_mcp_surface_is_small_and_handler_backed(self) -> None:
        ordered_names = [tool["name"] for tool in TOOLS]
        names = set(ordered_names)
        self.assertEqual(
            ordered_names,
            [
                "status",
                "approve_plan",
                "init_session",
                "inspect_state",
                "orchestrate",
                "research_prior_work",
                "import_prior_work",
                "authoring_round",
                "write_sections",
                "critique",
                "visual_audit",
                "quality_gate",
                "qa_loop",
                "qa_loop_step",
                "ralph_start",
                "compile_current_paper",
                "answer_human_needed",
                "export_current",
                "run_pipeline",
            ],
        )
        self.assertEqual(
            names,
            {
                "answer_human_needed",
                "approve_plan",
                "authoring_round",
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
                "visual_audit",
                "write_sections",
            },
        )
        self.assertEqual(names, set(TOOL_HANDLERS))

    def test_mcp_tool_contract_matches_snapshot(self) -> None:
        snapshot = Path(__file__).resolve().parent / "snapshots" / "mcp_tools.json"
        self.maxDiff = None
        self.assertEqual(TOOLS, json.loads(snapshot.read_text(encoding="utf-8")))

    def test_loop_engine_modules_import_from_new_packages(self) -> None:
        for module in (
            "paperorchestra.core.session",
            "paperorchestra.engine.pipeline",
            "paperorchestra.feedback.human_needed",
            "paperorchestra.interfaces.mcp.handlers",
            "paperorchestra.loop_engine.orchestra",
            "paperorchestra.loop_engine.quality.gate",
            "paperorchestra.loop_engine.quality.loop",
            "paperorchestra.loop_engine.ralph.bridge",
            "paperorchestra.manuscript.validator",
            "paperorchestra.orchestra.controller",
            "paperorchestra.research.literature",
            "paperorchestra.reviews.citation_model_writer",
            "paperorchestra.reviews.section_review",
            "paperorchestra.runtime.doctor",
            "paperorchestra.visual.page_layout_review",
        ):
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_root_package_stays_thin(self) -> None:
        root_py = {path.name for path in Path(paperorchestra.__file__).resolve().parent.glob("*.py")}
        self.assertLessEqual(root_py, {"__init__.py", "cli.py", "mcp_server.py"})

    def test_runtime_provider_facade_is_not_reintroduced(self) -> None:
        package_root = Path(paperorchestra.__file__).resolve().parent
        self.assertFalse((package_root / "runtime" / "providers.py").exists())

    def test_runtime_reports_repo_and_package_roots_after_module_split(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        package_root = Path(paperorchestra.__file__).resolve().parent
        context = package_context(repo_root)

        self.assertEqual(context["project_root"], str(repo_root))
        self.assertEqual(context["package_root"], str(package_root))
        self.assertIsNone(context["stale_install_warning"])

    def test_all_package_modules_import(self) -> None:
        failures = []
        for module in pkgutil.walk_packages(paperorchestra.__path__, prefix="paperorchestra."):
            if ".prompt_assets" in module.name:
                continue
            try:
                importlib.import_module(module.name)
            except Exception as exc:  # pragma: no cover - subTest reports concrete import failure
                failures.append(f"{module.name}: {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
