from __future__ import annotations

import json
import os
import math
import random
import shlex
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .transport_retry import is_retryable_transport_text


class OmxBridgeError(RuntimeError):
    pass



def _resolve_retry_attempts(env_var: str, default: int = 0) -> int:
    raw = os.environ.get(env_var)
    if raw in {None, ""}:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, 0), 10)


def _is_retryable_omx_failure(stdout: str, stderr: str) -> bool:
    _ = stdout
    return is_retryable_transport_text(stderr)


def _retry_backoff_seconds() -> float:
    base = _resolve_exec_timeout("PAPERO_OMX_RETRY_BACKOFF_SECONDS", 2.0, minimum=0.0, maximum=300.0)
    jitter = _resolve_exec_timeout("PAPERO_OMX_RETRY_JITTER_SECONDS", 0.0, minimum=0.0, maximum=300.0)
    return base + (random.uniform(0.0, jitter) if jitter > 0 else 0.0)


def _should_retry_omx_control(args: list[str]) -> bool:
    if not args:
        return False
    if args[0] == "status":
        return True
    if len(args) >= 2 and args[0] == "team" and args[1] == "status":
        return True
    return len(args) >= 3 and args[0] == "state" and args[1] == "read" and args[2] == "--json"


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
                    return subprocess.CompletedProcess(args=args, returncode=proc.returncode if proc.returncode is not None else 1, stdout=stdout or "", stderr=stderr or ""), True
                except subprocess.TimeoutExpired:
                    pass
            proc.kill()
            stdout, stderr = proc.communicate()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
    return subprocess.CompletedProcess(args=args, returncode=proc.returncode if proc.returncode is not None else 1, stdout=stdout or "", stderr=stderr or ""), timed_out


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


def _resolve_omx_model(model: str | None = None) -> str:
    return model or os.environ.get("PAPERO_OMX_MODEL") or "gpt-5.5"


def _resolve_omx_reasoning_effort(default: str = "low") -> str:
    return os.environ.get("PAPERO_OMX_REASONING_EFFORT") or default


def _format_omx_failure(args: list[str], return_code: int, stdout: str, stderr: str) -> str:
    stdout_text = stdout.strip() or "<empty>"
    stderr_text = stderr.strip() or "<empty>"
    return f"omx {shlex.join(args)} returned {return_code}: stderr={stderr_text} stdout={stdout_text}"


def _tmp_dir(cwd: str | Path | None) -> Path:
    root = Path(cwd or ".").resolve()
    path = root / ".paper-orchestra" / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_omx_tmp(cwd: str | Path | None, *, max_age_seconds: float = 0.0) -> dict[str, Any]:
    tmp_dir = _tmp_dir(cwd)
    now = time.time()
    removed: list[str] = []
    for path in tmp_dir.glob("omx-*"):
        if not path.is_file():
            continue
        if max_age_seconds > 0 and now - path.stat().st_mtime < max_age_seconds:
            continue
        path.unlink()
        removed.append(str(path))
    return {"tmp_dir": str(tmp_dir), "removed_count": len(removed), "removed": removed}


@dataclass(frozen=True)
class OmxWorkflowRecommendation:
    recommended_mode: str
    rationale: str
    suggested_commands: list[str]
    alternatives: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OmxTeamLaunchResult:
    team_name: str | None
    requested_workers: int
    agent_type: str
    task: str
    pid: int
    launch_status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OmxExecResult:
    output_path: str
    return_code: int
    stdout: str
    stderr: str
    prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_omx(args: list[str], *, cwd: str | Path | None, timeout_seconds: float | None = None) -> subprocess.CompletedProcess:
    resolved_timeout = timeout_seconds
    if resolved_timeout is None:
        resolved_timeout = _resolve_exec_timeout("PAPERO_OMX_CONTROL_TIMEOUT_SECONDS", 60.0)
    retryable_control = _should_retry_omx_control(args)
    grace = _resolve_exec_timeout("PAPERO_OMX_TIMEOUT_GRACE_SECONDS", 0.0, minimum=0.0, maximum=3600.0) if retryable_control else 0.0
    attempts = (_resolve_retry_attempts("PAPERO_OMX_RETRY_ATTEMPTS", 0) + 1) if retryable_control else 1
    failures: list[str] = []
    full_args = ["omx", *args]
    for attempt in range(1, attempts + 1):
        proc, timed_out = _run_with_soft_timeout(
            full_args,
            cwd=Path(cwd or ".").resolve(),
            timeout_seconds=resolved_timeout,
            grace_seconds=grace,
        )
        if proc.returncode == 0:
            return proc
        if timed_out:
            failures.append(f"attempt {attempt}/{attempts}: timed out after {resolved_timeout:g}s + grace {grace:g}s")
            retryable = _is_retryable_omx_failure(proc.stdout, proc.stderr)
        else:
            failures.append(f"attempt {attempt}/{attempts}: returned {proc.returncode}: stderr={proc.stderr.strip() or '<empty>'}")
            retryable = _is_retryable_omx_failure(proc.stdout, proc.stderr)
        if retryable_control and retryable and attempt < attempts:
            backoff = _retry_backoff_seconds()
            if backoff > 0:
                time.sleep(backoff)
            continue
        if timed_out:
            detail = "; ".join(failures)
            raise OmxBridgeError(f"omx {shlex.join(args)} timed out after retryable transport handling: {detail}")
        raise OmxBridgeError(_format_omx_failure(args, proc.returncode, proc.stdout, proc.stderr))
    raise OmxBridgeError(f"omx {shlex.join(args)} failed without producing a result")


def _team_state_root(cwd: str | Path | None) -> Path:
    return Path(cwd or ".").resolve() / ".omx" / "state" / "team"


def list_omx_teams(*, cwd: str | Path | None) -> list[str]:
    root = _team_state_root(cwd)
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def omx_status(*, cwd: str | Path | None) -> dict[str, str]:
    proc = _run_omx(["status"], cwd=cwd)
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return {f"line_{i+1}": line for i, line in enumerate(lines)}


def omx_state(operation: str, payload: dict[str, Any] | None = None, *, cwd: str | Path | None) -> dict[str, Any]:
    args = ["state", operation, "--json"]
    if payload is not None:
        args.extend(["--input", json.dumps(payload, ensure_ascii=False)])
    proc = _run_omx(args, cwd=cwd)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OmxBridgeError("Failed to parse omx state JSON output") from exc


def omx_explore(prompt: str, *, cwd: str | Path | None) -> str:
    proc = _run_omx(["explore", "--prompt", prompt], cwd=cwd)
    return proc.stdout.strip()


def omx_team_status(team_name: str, *, cwd: str | Path | None, tail_lines: int | None = None) -> dict[str, Any]:
    args = ["team", "status", team_name, "--json"]
    if tail_lines is not None:
        args.extend(["--tail-lines", str(tail_lines)])
    proc = _run_omx(args, cwd=cwd)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OmxBridgeError("Failed to parse omx team status JSON output") from exc


def launch_omx_team(
    task: str,
    *,
    workers: int = 2,
    agent_type: str = "executor",
    cwd: str | Path | None,
    timeout_seconds: float = 15.0,
) -> OmxTeamLaunchResult:
    before = set(list_omx_teams(cwd=cwd))
    proc = subprocess.Popen(
        ["omx", "team", f"{workers}:{agent_type}", task],
        cwd=Path(cwd or ".").resolve(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        after = set(list_omx_teams(cwd=cwd))
        created = sorted(after - before)
        if created:
            return OmxTeamLaunchResult(
                team_name=created[-1],
                requested_workers=workers,
                agent_type=agent_type,
                task=task,
                pid=proc.pid,
                launch_status="started",
                message="OMX team state was detected successfully.",
            )
        time.sleep(0.5)
    return OmxTeamLaunchResult(
        team_name=None,
        requested_workers=workers,
        agent_type=agent_type,
        task=task,
        pid=proc.pid,
        launch_status="unknown",
        message="OMX launch command was started, but no team state appeared before timeout. Check `omx status`, `list_omx_teams`, or run the suggested team command manually.",
    )


def shutdown_omx_team(team_name: str, *, cwd: str | Path | None, force: bool = True) -> dict[str, Any]:
    args = ["team", "shutdown", team_name]
    if force:
        args.append("--force")
    proc = _run_omx(args, cwd=cwd)
    return {"team_name": team_name, "output": proc.stdout.strip()}




def _run_omx_exec_command(
    args: list[str],
    *,
    root: Path,
    prompt: str,
    output_path: Path,
    timeout_seconds: float,
    failure_args: list[str],
) -> subprocess.CompletedProcess:
    # `omx exec --full-auto` is repo-scoped and not replay-safe. We provide a
    # soft timeout grace window for in-place Codex reconnects, then fail fast.
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
            "full-auto exec replay is disabled because the command is not idempotent"
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
    tmp_dir = _tmp_dir(root)
    timeout_seconds = _resolve_exec_timeout("PAPERO_OMX_EXEC_TIMEOUT_SECONDS", timeout_seconds)
    model = _resolve_omx_model(model)
    reasoning_effort = _resolve_omx_reasoning_effort()
    with tempfile.NamedTemporaryFile(prefix="omx-exec-", suffix=".txt", dir=tmp_dir, delete=False) as handle:
        output_path = Path(handle.name)
    proc = _run_omx_exec_command(
        [
            "omx",
            "exec",
            "--full-auto",
            "--skip-git-repo-check",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            "-C",
            str(root),
            "-o",
            str(output_path),
            "-",
        ],
        root=root,
        prompt=prompt,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
        failure_args=["exec"],
    )
    return OmxExecResult(
        output_path=str(output_path),
        return_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        prompt=prompt,
    )


def omx_exec_json_completion(
    prompt: str,
    schema: dict[str, Any],
    *,
    cwd: str | Path | None,
    timeout_seconds: float = 180.0,
    model: str | None = None,
) -> OmxExecResult:
    root = Path(cwd or ".").resolve()
    tmp_dir = _tmp_dir(root)
    timeout_seconds = _resolve_exec_timeout("PAPERO_OMX_EXEC_TIMEOUT_SECONDS", timeout_seconds)
    model = _resolve_omx_model(model)
    reasoning_effort = _resolve_omx_reasoning_effort()
    with tempfile.NamedTemporaryFile(prefix="omx-schema-", suffix=".json", dir=tmp_dir, delete=False) as schema_file:
        Path(schema_file.name).write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        schema_path = Path(schema_file.name)
    with tempfile.NamedTemporaryFile(prefix="omx-exec-", suffix=".json", dir=tmp_dir, delete=False) as out_file:
        output_path = Path(out_file.name)
    proc = _run_omx_exec_command(
        [
            "omx",
            "exec",
            "--full-auto",
            "--skip-git-repo-check",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{reasoning_effort}"',
            "-C",
            str(root),
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-",
        ],
        root=root,
        prompt=prompt,
        output_path=output_path,
        timeout_seconds=timeout_seconds,
        failure_args=["exec", "--output-schema"],
    )
    return OmxExecResult(
        output_path=str(output_path),
        return_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        prompt=prompt,
    )


def recommend_omx_workflow(
    task: str,
    *,
    need_parallel: bool = False,
    need_persistence: bool = False,
    need_review_loop: bool = False,
) -> OmxWorkflowRecommendation:
    normalized = task.lower()
    if need_parallel or any(token in normalized for token in ["parallel", "multi-agent", "swarm", "team"]):
        return OmxWorkflowRecommendation(
            recommended_mode="team",
            rationale="The task benefits from durable parallel worker coordination and explicit team state.",
            suggested_commands=[f'omx team 3:executor "{task}"', f'omx team status <team-name> --json'],
            alternatives=[f'omx explore --prompt {shlex.quote(task)}', f'omx ralph "{task}"'],
        )
    if need_persistence or need_review_loop or any(token in normalized for token in ["keep going", "persistent", "verify", "review loop", "refine"]):
        return OmxWorkflowRecommendation(
            recommended_mode="ralph",
            rationale="The task needs persistent single-owner execution with repeated verification and progress continuity.",
            suggested_commands=[f'omx ralph "{task}"', 'omx status'],
            alternatives=[f'omx explore --prompt {shlex.quote(task)}', f'omx team 2:executor "{task}"'],
        )
    return OmxWorkflowRecommendation(
        recommended_mode="explore",
        rationale="The task looks read-heavy or planning-heavy, so OMX explore is the lightest good first step.",
        suggested_commands=[f'omx explore --prompt {shlex.quote(task)}', 'omx status'],
        alternatives=[f'omx ralph "{task}"', f'omx team 2:executor "{task}"'],
    )
