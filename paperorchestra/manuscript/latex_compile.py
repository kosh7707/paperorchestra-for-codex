from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

from paperorchestra.manuscript.latex_commands import (
    _parse_sandbox_command,
    _run_wrapped_command,
    _summarize_compile_warnings,
)
from paperorchestra.manuscript.latex_compile_runner import LatexCompileRun
from paperorchestra.manuscript.latex_bibliography_inputs import (
    _copy_bibliography_input_files,
    _prepare_compile_inputs,
    _referenced_bibliography_stems,
)
from paperorchestra.manuscript.latex_input_env import _force_latexmk_rerun_command, _prepend_path
from paperorchestra.manuscript.latex_input_roots import _infer_project_root_from_source, _infer_run_root_from_source
from paperorchestra.manuscript.latex_messages import compile_opt_in_error_message, missing_compile_environment_message
from paperorchestra.manuscript.latex_models import CompileResult, LatexBuildError
from paperorchestra.manuscript.latex_safety import blocked_latex_pattern
from paperorchestra.runtime.compile_env import ensure_sandbox_wrapper, inspect_compile_environment


def validate_latex_source(source_text: str) -> None:
    blocked_pattern = blocked_latex_pattern(source_text)
    if blocked_pattern:
        raise LatexBuildError(f"LaTeX source contains a blocked pattern: {blocked_pattern}")


def compile_latex_with_report(source: str | Path, *, workdir: str | Path, output_log: str | Path) -> CompileResult:
    return LatexCompileRun(source=source, workdir=workdir, output_log=output_log, stage=sys.modules[__name__]).run()


def compile_latex(source: str | Path, *, workdir: str | Path, output_log: str | Path) -> Path:
    report = compile_latex_with_report(source, workdir=workdir, output_log=output_log)
    if not report.pdf_exists:
        raise LatexBuildError(f"LaTeX build failed. See log: {report.log_path}")
    if not report.clean:
        raise LatexBuildError(f"LaTeX build completed with unresolved issues. See log: {report.log_path}")
    return Path(report.pdf_path)


__all__ = ["LatexCompileRun", "compile_latex", "compile_latex_with_report", "validate_latex_source"]
