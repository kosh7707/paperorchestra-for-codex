from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def communicate_with_soft_timeout(
    proc: subprocess.Popen,
    *,
    input_data: Any = None,
    timeout_seconds: float | None,
    grace_seconds: float,
) -> tuple[Any, Any, bool]:
    timed_out = False
    try:
        stdout, stderr = proc.communicate(input=input_data, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        if grace_seconds > 0:
            try:
                stdout, stderr = proc.communicate(timeout=grace_seconds)
                return stdout, stderr, True
            except subprocess.TimeoutExpired:
                pass
        proc.kill()
        stdout, stderr = proc.communicate()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    return stdout, stderr, timed_out


def run_with_soft_timeout(
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    grace_seconds: float,
    input_text: str | None = None,
) -> tuple[subprocess.CompletedProcess, bool]:
    timed_out = False
    with subprocess.Popen(
        args,
        cwd=cwd,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as proc:
        stdout, stderr, timed_out = communicate_with_soft_timeout(
            proc,
            input_data=input_text,
            timeout_seconds=timeout_seconds,
            grace_seconds=grace_seconds,
        )
    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode if proc.returncode is not None else 1,
        stdout=stdout or "",
        stderr=stderr or "",
    ), timed_out
