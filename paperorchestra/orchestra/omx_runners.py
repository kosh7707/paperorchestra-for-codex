from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class OmxCommandResult:
    return_code: int
    stdout: str = ""
    stderr: str = ""


class OmxCommandRunner(Protocol):
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        ...


@dataclass
class FakeOmxRunner:
    results: list[OmxCommandResult] = field(default_factory=list)
    exception: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        self.calls.append({"argv": list(argv), "cwd": str(cwd), "timeout_seconds": timeout_seconds})
        if self.exception is not None:
            raise self.exception
        if self.results:
            return self.results.pop(0)
        return OmxCommandResult(return_code=0, stdout="{}")


@dataclass(frozen=True)
class SubprocessOmxRunner:
    binary: str = "omx"

    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        resolved_argv = list(argv)
        if resolved_argv and resolved_argv[0] == "omx":
            resolved_argv[0] = self.binary
        try:
            proc = subprocess.run(
                resolved_argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("omx_command_timeout") from exc
        return OmxCommandResult(return_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
