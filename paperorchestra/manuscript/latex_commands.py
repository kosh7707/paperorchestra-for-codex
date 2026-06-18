from __future__ import annotations

import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path

from paperorchestra.manuscript.latex_models import LatexBuildError


def _parse_sandbox_command(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        raise LatexBuildError("PAPERO_TEX_SANDBOX_CMD must not be empty.")
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) for item in parsed):
            raise LatexBuildError("PAPERO_TEX_SANDBOX_CMD JSON must be a non-empty string array.")
        return parsed
    return shlex.split(raw)


def _summarize_compile_warnings(log_text: str) -> list[str]:
    if "[REFERENCE STABILIZATION PASS]" in log_text:
        log_text = log_text.split("[REFERENCE STABILIZATION PASS]", 1)[1]
    if "[POST-BIBTEX LATEXMK PASS]" in log_text:
        log_text = log_text.split("[POST-BIBTEX LATEXMK PASS]", 1)[1]
    warnings: list[str] = []
    lowered = log_text.lower()
    if "failed to resolve 1 reference" in lowered or "undefined reference" in lowered:
        warnings.append("undefined references detected")
    if (
        re.search(r"failed to resolve\s+\d+\s+citation", lowered)
        or "undefined citations" in lowered
        or "there were undefined citations" in lowered
    ):
        warnings.append("undefined citations detected")
    if "unknown graphics extension" in lowered:
        warnings.append("unknown graphics extension encountered")
    return warnings


def _latex_timeout_seconds(timeout: int | float | None = None) -> int:
    if timeout is not None:
        value = timeout
    else:
        raw = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC", "").strip()
        if not raw:
            return 30
        try:
            value = float(raw)
        except ValueError as exc:
            raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be a number of seconds between 1 and 3600.") from exc
    if not math.isfinite(float(value)):
        raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be a finite number of seconds between 1 and 3600.")
    if value < 1 or value > 3600:
        raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be between 1 and 3600 seconds.")
    return int(value)


def _run_wrapped_command(full_cmd: list[str], *, env: dict[str, str], cwd: Path, timeout: int | float | None = None) -> subprocess.CompletedProcess:
    timeout_seconds = _latex_timeout_seconds(timeout)
    try:
        return subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
            env=env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise LatexBuildError(f"LaTeX build timed out after {timeout_seconds} seconds.") from exc
