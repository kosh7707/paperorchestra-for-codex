from __future__ import annotations

import json
import math
import os
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class OmxBridgeError(RuntimeError):
    pass


def _run_with_soft_timeout(
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
        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if grace_seconds > 0:
                try:
                    stdout, stderr = proc.communicate(timeout=grace_seconds)
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=proc.returncode if proc.returncode is not None else 1,
                        stdout=stdout or "",
                        stderr=stderr or "",
                    ), True
                except subprocess.TimeoutExpired:
                    pass
            proc.kill()
            stdout, stderr = proc.communicate()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode if proc.returncode is not None else 1,
        stdout=stdout or "",
        stderr=stderr or "",
    ), timed_out


def _resolve_exec_timeout(env_var: str, default: float, *, minimum: float = 1.0, maximum: float = 3600.0) -> float:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not math.isfinite(value) or value < minimum:
        return default
    return min(value, maximum)


def _resolve_omx_model(model: str | None = None) -> str | None:
    return model or os.environ.get("PAPERO_OMX_MODEL") or None


def _resolve_omx_reasoning_effort(default: str | None = None) -> str | None:
    return os.environ.get("PAPERO_OMX_REASONING_EFFORT") or default


def _append_omx_model_flags(args: list[str], *, model: str | None, reasoning_effort: str | None) -> list[str]:
    if model:
        args.extend(["-m", model])
    if reasoning_effort:
        args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    return args


def _format_omx_failure(args: list[str], return_code: int, stdout: str, stderr: str) -> str:
    stdout_text = stdout.strip() or "<empty>"
    stderr_text = stderr.strip() or "<empty>"
    return f"omx {shlex.join(args)} returned {return_code}: stderr={stderr_text} stdout={stdout_text}"


def _tmp_dir(cwd: str | Path | None) -> Path:
    root = Path(cwd or ".").resolve()
    path = root / ".paper-orchestra" / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class OmxExecResult:
    output_path: str
    return_code: int
    stdout: str
    stderr: str
    prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_omx_exec_command(
    args: list[str],
    *,
    root: Path,
    prompt: str,
    output_path: Path,
    timeout_seconds: float,
    failure_args: list[str],
) -> subprocess.CompletedProcess:
    # `omx exec --dangerously-bypass-approvals-and-sandbox` is repo-scoped and not replay-safe.
    # A soft grace window allows in-place Codex reconnects, then fails fast instead of retrying.
    grace = _resolve_exec_timeout("PAPERO_OMX_TIMEOUT_GRACE_SECONDS", 0.0, minimum=0.0, maximum=3600.0)
    if output_path.exists():
        output_path.write_text("", encoding="utf-8")
    proc, timed_out = _run_with_soft_timeout(
        args,
        cwd=root,
        input_text=prompt,
        timeout_seconds=timeout_seconds,
        grace_seconds=grace,
    )
    if proc.returncode == 0:
        return proc
    if timed_out:
        raise OmxBridgeError(
            f"omx {shlex.join(failure_args)} timed out after {timeout_seconds:g}s + grace {grace:g}s; "
            "omx exec replay is disabled because the command is not idempotent"
        )
    raise OmxBridgeError(_format_omx_failure(failure_args, proc.returncode, proc.stdout, proc.stderr))


def omx_exec_completion(
    prompt: str,
    *,
    cwd: str | Path | None,
    timeout_seconds: float = 180.0,
    model: str | None = None,
) -> OmxExecResult:
    root = Path(cwd or ".").resolve()
    timeout_seconds = _resolve_exec_timeout("PAPERO_OMX_EXEC_TIMEOUT_SECONDS", timeout_seconds)
    with tempfile.NamedTemporaryFile(prefix="omx-exec-", suffix=".txt", dir=_tmp_dir(root), delete=False) as out_file:
        output_path = Path(out_file.name)
    args = _append_omx_model_flags(
        ["omx", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
        model=_resolve_omx_model(model),
        reasoning_effort=_resolve_omx_reasoning_effort(),
    )
    args.extend(["-C", str(root), "-o", str(output_path), "-"])
    proc = _run_omx_exec_command(args, root=root, prompt=prompt, output_path=output_path, timeout_seconds=timeout_seconds, failure_args=["exec"])
    return OmxExecResult(output_path=str(output_path), return_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, prompt=prompt)


def omx_exec_json_completion(
    prompt: str,
    schema: dict[str, Any],
    *,
    cwd: str | Path | None,
    timeout_seconds: float = 180.0,
    model: str | None = None,
) -> OmxExecResult:
    root = Path(cwd or ".").resolve()
    timeout_seconds = _resolve_exec_timeout("PAPERO_OMX_EXEC_TIMEOUT_SECONDS", timeout_seconds)
    with tempfile.NamedTemporaryFile(prefix="omx-schema-", suffix=".json", dir=_tmp_dir(root), delete=False) as schema_file:
        schema_path = Path(schema_file.name)
    schema_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    with tempfile.NamedTemporaryFile(prefix="omx-exec-", suffix=".json", dir=_tmp_dir(root), delete=False) as out_file:
        output_path = Path(out_file.name)
    args = _append_omx_model_flags(
        ["omx", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
        model=_resolve_omx_model(model),
        reasoning_effort=_resolve_omx_reasoning_effort(),
    )
    args.extend(["-C", str(root), "--output-schema", str(schema_path), "-o", str(output_path), "-"])
    proc = _run_omx_exec_command(
        args,
        root=root,
        prompt=prompt,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
        failure_args=["exec", "--output-schema"],
    )
    return OmxExecResult(output_path=str(output_path), return_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, prompt=prompt)
