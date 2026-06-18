from __future__ import annotations

from typing import Any


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
