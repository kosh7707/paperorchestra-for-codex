from __future__ import annotations

import argparse
from typing import Any

from paperorchestra import __version__
from paperorchestra.interfaces.cli_parser_sections.authoring import register_authoring_commands
from paperorchestra.interfaces.cli_parser_sections.quality import register_quality_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperorchestra",
        description="PaperOrchestra CLI: status, research, critic review, authoring, QA loop, and OMX handoff.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_session_commands(subparsers)
    register_orchestration_commands(subparsers)
    register_authoring_commands(subparsers)
    register_quality_commands(subparsers)

    return parser


def register_session_commands(subparsers: Any) -> None:
    init_parser = subparsers.add_parser("init", help="Initialize a PaperOrchestra session")
    init_parser.add_argument("--idea", required=True)
    init_parser.add_argument("--experimental-log", required=True)
    init_parser.add_argument("--template", required=True)
    init_parser.add_argument("--guidelines", required=True)
    init_parser.add_argument("--figures-dir")
    init_parser.add_argument("--cutoff-date")
    init_parser.add_argument("--venue")
    init_parser.add_argument("--page-limit", type=int)
    init_parser.add_argument("--allow-outside-workspace", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show current session state")
    status_parser.add_argument("--json", action="store_true")
    status_parser.add_argument("--summary", action="store_true")

    export_parser = subparsers.add_parser("export-current", help="Copy current manuscript outputs to a destination directory")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--include-all-artifacts", action="store_true")
    export_parser.add_argument("--json", action="store_true")

    subparsers.add_parser("compile", help="Compile the current manuscript")

    environment_parser = subparsers.add_parser("environment", help="Show environment-variable and readiness inventory")
    environment_parser.add_argument("--json", action="store_true")
    environment_parser.add_argument("--summary", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Run a pre-flight environment check")
    doctor_parser.add_argument("--omx-deep", action="store_true")
    doctor_parser.add_argument("--omx-timeout", type=float, default=10.0)


def register_orchestration_commands(subparsers: Any) -> None:
    inspect_state_parser = subparsers.add_parser("inspect-state", help="Inspect material readiness and the next orchestration action")
    inspect_state_parser.add_argument("--material")
    inspect_state_parser.add_argument("--json", action="store_true")

    orchestrate_parser = subparsers.add_parser("orchestrate", help="Run the orchestrator until the next bounded action or stop")
    orchestrate_parser.add_argument("--material")
    orchestrate_mode = orchestrate_parser.add_mutually_exclusive_group()
    orchestrate_mode.add_argument("--execute-local", action="store_true")
    orchestrate_mode.add_argument("--plan-full-loop", action="store_true")
    orchestrate_mode.add_argument("--execute-omx", action="store_true")
    orchestrate_parser.add_argument("--write-evidence", action="store_true")
    orchestrate_parser.add_argument("--evidence-output")
    orchestrate_parser.add_argument("--json", action="store_true")
