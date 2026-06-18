from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from paperorchestra.interfaces.cli_commands.authoring import (
    handle_critique,
    handle_import_prior_work,
    handle_research_prior_work,
    handle_run,
    handle_write_sections,
)
from paperorchestra.interfaces.cli_commands.orchestration import handle_inspect_state, handle_orchestrate
from paperorchestra.interfaces.cli_commands.quality import (
    handle_answer_human_needed,
    handle_qa_loop,
    handle_qa_loop_step,
    handle_quality_gate,
    handle_ralph_start,
)
from paperorchestra.interfaces.cli_commands.session import (
    handle_compile,
    handle_doctor,
    handle_environment,
    handle_export_current,
    handle_init,
    handle_status,
)

CliHandler = Callable[[Path, argparse.Namespace], int]

CLI_HANDLERS: dict[str, CliHandler] = {
    "init": handle_init,
    "status": handle_status,
    "inspect-state": handle_inspect_state,
    "orchestrate": handle_orchestrate,
    "answer-human-needed": handle_answer_human_needed,
    "export-current": handle_export_current,
    "research-prior-work": handle_research_prior_work,
    "import-prior-work": handle_import_prior_work,
    "write-sections": handle_write_sections,
    "compile": handle_compile,
    "environment": handle_environment,
    "doctor": handle_doctor,
    "critique": handle_critique,
    "quality-gate": handle_quality_gate,
    "qa-loop": handle_qa_loop,
    "qa-loop-step": handle_qa_loop_step,
    "ralph-start": handle_ralph_start,
    "run": handle_run,
}


def handle_cli_command(args: argparse.Namespace, *, cwd: Path, parser: argparse.ArgumentParser) -> int:
    handler = CLI_HANDLERS.get(args.command)
    if handler is None:
        parser.error(f"Unhandled command: {args.command}")
        return 2
    return handler(cwd, args)
