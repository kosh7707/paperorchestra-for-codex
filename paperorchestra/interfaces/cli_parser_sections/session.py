from __future__ import annotations

from typing import Any


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
