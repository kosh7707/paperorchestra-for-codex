from __future__ import annotations

from pathlib import Path

from paperorchestra.runtime.compile_env import ensure_sandbox_wrapper, inspect_compile_environment
from paperorchestra.manuscript.latex_commands import (
    _latex_timeout_seconds,
    _parse_sandbox_command,
    _run_wrapped_command,
    _summarize_compile_warnings,
)
from paperorchestra.manuscript.latex_compile import compile_latex, compile_latex_with_report, validate_latex_source
from paperorchestra.manuscript.latex_messages import compile_opt_in_error_message, missing_compile_environment_message
from paperorchestra.manuscript.latex_models import CompileResult, LatexBuildError


def _compile_opt_in_error_message() -> str:
    return compile_opt_in_error_message()


def _missing_compile_environment_message(project_root: Path) -> str:
    return missing_compile_environment_message(project_root, inspect_compile_environment)


__all__ = [
    "CompileResult",
    "LatexBuildError",
    "_compile_opt_in_error_message",
    "_latex_timeout_seconds",
    "_missing_compile_environment_message",
    "_parse_sandbox_command",
    "_run_wrapped_command",
    "_summarize_compile_warnings",
    "compile_latex",
    "compile_latex_with_report",
    "ensure_sandbox_wrapper",
    "inspect_compile_environment",
    "validate_latex_source",
]
