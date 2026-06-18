from __future__ import annotations

import argparse

from paperorchestra import __version__
from paperorchestra.interfaces.cli_parser_sections import (
    register_authoring_commands,
    register_orchestration_commands,
    register_quality_commands,
    register_session_commands,
)


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
