from __future__ import annotations

from pathlib import Path
from typing import Callable, Any


def compile_opt_in_error_message() -> str:
    return """LaTeX compilation is disabled by default.

To inspect whether this machine can compile:
  paperorchestra environment --summary

To intentionally compile:
  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"""


def missing_compile_environment_message(project_root: Path, inspect_compile_environment: Callable[..., Any]) -> str:
    try:
        report = inspect_compile_environment(project_root, auto_configure_wrapper=False)
    except Exception as exc:
        return (
            "compile environment is not ready.\n\n"
            f"Could not inspect compile environment automatically: {type(exc).__name__}: {exc}\n\n"
            "Run:\n"
            "  paperorchestra environment --summary\n"
            "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"
        )

    sandbox_state = report.sandbox_tool or "missing (bwrap/firejail/nsjail or PAPERO_TEX_SANDBOX_CMD)"
    wrapper_state = report.sandbox_wrapper_path or "not configured"
    engine_state = report.latex_engine or "missing (latexmk/pdflatex/tectonic)"
    missing: list[str] = []
    if not report.latex_engine:
        missing.append("LaTeX engine: latexmk, pdflatex, or tectonic")
    if not report.sandbox_wrapper_path:
        missing.append("usable sandbox wrapper: bwrap, firejail, nsjail, or PAPERO_TEX_SANDBOX_CMD")
    missing_lines = "\n".join(f"  - {item}" for item in missing) if missing else "  - compile readiness probe did not produce a sandbox wrapper"

    return (
        "compile environment is not ready.\n\n"
        "Missing:\n"
        f"{missing_lines}\n\n"
        "Detected:\n"
        f"  LaTeX engine: {engine_state}\n"
        f"  Usable sandbox: {sandbox_state}\n"
        f"  Sandbox wrapper: {wrapper_state}\n\n"
        "Run:\n"
        "  paperorchestra environment --summary\n"
        "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"
    )
