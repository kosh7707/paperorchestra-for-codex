from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from typing import Any

from .io_utils import read_json, write_json
from .models import utc_now_iso
from .quality_loop_plan_logic import _quality_eval_ready
from .quality_loop_utils import _file_sha256
from .session import artifact_path, get_current_session_id, load_session, project_root, runtime_root

_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
JOB_ID_RE = re.compile(r"^job-[a-f0-9]{12}$")


@dataclass
class JobState:
    job_id: str
    kind: str
    cwd: str
    created_at: str
    updated_at: str
    status: str
    session_id: str | None = None
    pid: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    return_code: int | None = None
    log_path: str | None = None
    result_path: str | None = None
    spec_path: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobState":
        return cls(**payload)


def jobs_root(cwd: str | Path | None = None) -> Path:
    path = runtime_root(cwd) / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validated_job_id(job_id: str) -> str:
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError(f"Invalid job_id: {job_id}")
    return job_id


def job_dir(cwd: str | Path | None, job_id: str) -> Path:
    root = jobs_root(cwd).resolve()
    path = (root / _validated_job_id(job_id)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Invalid job path for id: {job_id}") from exc
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_state_path(cwd: str | Path | None, job_id: str) -> Path:
    return job_dir(cwd, job_id) / "state.json"


def job_spec_path(cwd: str | Path | None, job_id: str) -> Path:
    return job_dir(cwd, job_id) / "spec.json"


def load_job(cwd: str | Path | None, job_id: str) -> JobState:
    return JobState.from_dict(read_json(job_state_path(cwd, job_id)))


def save_job(cwd: str | Path | None, state: JobState) -> Path:
    state.updated_at = utc_now_iso()
    path = job_state_path(cwd, state.job_id)
    write_json(path, state.to_dict())
    return path


def _qa_readiness_snapshot(cwd: str | Path | None, session_id: str) -> dict[str, Any]:
    plan_path = artifact_path(cwd, "qa-loop.plan.json", session_id)
    verdict = None
    readiness_valid = False
    invalid_reason = None
    if plan_path.exists():
        try:
            payload = read_json(plan_path)
            if isinstance(payload, dict):
                verdict = payload.get("verdict")
                if verdict == "ready_for_human_finalization":
                    readiness_valid, invalid_reason = _ready_plan_is_current(cwd, session_id, payload)
        except Exception:
            verdict = None
            invalid_reason = "qa_loop_plan_unreadable"
    return {
        "qa_loop_plan": str(plan_path) if plan_path.exists() else None,
        "verdict": verdict,
        "ready_for_human_finalization": verdict == "ready_for_human_finalization" and readiness_valid,
        "readiness_source": "qa-loop.plan.json" if verdict else "missing_qa_loop_plan",
        "readiness_valid": readiness_valid,
        "readiness_invalid_reason": invalid_reason,
    }


def _path_ref_parts(ref: Any) -> tuple[Path | None, str | None]:
    if not isinstance(ref, str) or not ref:
        return None, None
    path_text, marker, sha = ref.rpartition("@sha256:")
    if marker:
        return Path(path_text), sha
    return Path(ref), None


def _ready_plan_is_current(cwd: str | Path | None, session_id: str, plan: dict[str, Any]) -> tuple[bool, str | None]:
    if plan.get("schema_version") != "qa-loop-plan/2":
        return False, "qa_loop_plan_schema_invalid"
    if plan.get("session_id") != session_id:
        return False, "qa_loop_plan_session_mismatch"
    if plan.get("repair_actions"):
        return False, "qa_loop_plan_has_repair_actions"
    quality_ref = ((plan.get("reads") or {}).get("quality_eval") if isinstance(plan.get("reads"), dict) else None)
    quality_path, expected_sha = _path_ref_parts(quality_ref)
    if quality_path is None or not quality_path.exists():
        return False, "quality_eval_missing"
    actual_sha = _file_sha256(quality_path)
    if expected_sha and actual_sha != expected_sha:
        return False, "quality_eval_sha_mismatch"
    try:
        quality_eval = read_json(quality_path)
    except Exception:
        return False, "quality_eval_unreadable"
    if not isinstance(quality_eval, dict):
        return False, "quality_eval_invalid"
    session = load_session(cwd, session_id)
    current_manuscript_sha = _file_sha256(session.artifacts.paper_full_tex)
    eval_manuscript_sha = str(quality_eval.get("manuscript_hash") or "").removeprefix("sha256:")
    if current_manuscript_sha and eval_manuscript_sha != current_manuscript_sha:
        return False, "quality_eval_manuscript_stale"
    if not _quality_eval_ready(quality_eval, accept_mixed_provenance=False):
        return False, "quality_eval_not_ready"
    citation_identity = ((plan.get("source_artifacts") or {}).get("citation_review_identity_status") if isinstance(plan.get("source_artifacts"), dict) else None)
    if citation_identity != "pass":
        return False, "citation_support_review_stale"
    return True, None


def _job_env(cwd: str | Path | None) -> dict[str, str]:
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parent.parent)
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = root if not current else f"{root}:{current}"
    return env


def start_run_job(
    cwd: str | Path | None,
    *,
    provider: str = "mock",
    provider_command: str | None = None,
    discovery_mode: str = "model",
    verify_mode: str = "live",
    verify_error_policy: str = "skip",
    verify_fallback_mode: str = "none",
    require_live_verification: bool = False,
    refine_iterations: int = 1,
    compile_paper: bool = False,
    runtime_mode: str = "compatibility",
) -> dict[str, Any]:
    job_id = f"job-{os.urandom(6).hex()}"
    root = project_root(cwd)
    directory = job_dir(cwd, job_id)
    state = JobState(
        job_id=job_id,
        kind="run_pipeline",
        cwd=str(root),
        session_id=get_current_session_id(cwd) if (runtime_root(cwd) / "current_session.txt").exists() else None,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
        status="queued",
        log_path=str(directory / "job.log"),
        result_path=str(directory / "result.json"),
        spec_path=str(directory / "spec.json"),
        notes=["Background pipeline job created."],
    )
    spec = {
        "kind": "run_pipeline",
        "cwd": str(root),
        "session_id": state.session_id,
        "provider": provider,
        "provider_command": provider_command,
        "discovery_mode": discovery_mode,
        "verify_mode": verify_mode,
        "verify_error_policy": verify_error_policy,
        "verify_fallback_mode": verify_fallback_mode,
        "require_live_verification": bool(require_live_verification),
        "refine_iterations": int(refine_iterations),
        "compile_paper": bool(compile_paper),
        "runtime_mode": runtime_mode,
    }
    write_json(state.spec_path, spec)
    save_job(cwd, state)

    command = [sys.executable, "-m", "paperorchestra.job_runner", state.spec_path, state.log_path, state.result_path, job_state_path(cwd, job_id)]
    log_handle = open(state.log_path, "a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(root),
        env=_job_env(cwd),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    log_handle.close()
    _ACTIVE_PROCESSES[job_id] = process

    state.status = "running"
    state.pid = process.pid
    state.started_at = utc_now_iso()
    state.notes.append(f"Started runner pid={process.pid}.")
    save_job(cwd, state)
    return state.to_dict()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def get_job_status(cwd: str | Path | None, job_id: str) -> dict[str, Any]:
    state = load_job(cwd, job_id)
    process = _ACTIVE_PROCESSES.get(job_id)
    if process is not None:
        return_code = process.poll()
        if return_code is not None:
            process.wait()
            _ACTIVE_PROCESSES.pop(job_id, None)
            state = load_job(cwd, job_id)
            if state.status == "running":
                state.return_code = return_code
                state.completed_at = state.completed_at or utc_now_iso()
                if return_code == 0 and state.result_path and Path(state.result_path).exists():
                    state.status = "succeeded"
                else:
                    state.status = "failed"
                    state.error = state.error or f"Background runner exited with code {return_code}."
                save_job(cwd, state)
    if state.status == "running" and state.pid and not _pid_alive(state.pid):
        if state.result_path and Path(state.result_path).exists():
            state.status = "succeeded"
            state.return_code = 0
            state.completed_at = state.completed_at or utc_now_iso()
        else:
            state.status = "failed"
            state.error = state.error or "Background runner exited without writing a result."
            state.return_code = state.return_code if state.return_code is not None else 1
            state.completed_at = state.completed_at or utc_now_iso()
        save_job(cwd, state)
    payload = state.to_dict()
    if state.result_path and Path(state.result_path).exists():
        try:
            payload["result"] = read_json(state.result_path)
        except Exception:
            payload["result"] = {"path": state.result_path}
    try:
        session = load_session(cwd, state.session_id) if state.session_id else None
    except Exception:
        session = None
    if session is not None:
        qa_readiness = _qa_readiness_snapshot(cwd, session.session_id)
        payload["session_progress"] = {
            "session_id": session.session_id,
            "current_phase": session.current_phase,
            "active_artifact": session.active_artifact,
            "refinement_iteration": session.refinement_iteration,
            "qa_readiness": qa_readiness,
            "ready_for_human_finalization": qa_readiness["ready_for_human_finalization"],
            "notes_tail": session.notes[-5:],
        }
    return payload


def list_jobs(cwd: str | Path | None, *, limit: int = 20) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(jobs_root(cwd).glob("job-*/state.json"), reverse=True):
        try:
            state = JobState.from_dict(read_json(path))
            entries.append(state.to_dict())
        except Exception:
            continue
    return {"jobs": entries[:limit]}


def tail_job_log(cwd: str | Path | None, job_id: str, *, lines: int = 40) -> dict[str, Any]:
    state = load_job(cwd, job_id)
    path = Path(state.log_path) if state.log_path else None
    if path is None or not path.exists():
        return {"job_id": job_id, "log_path": str(path) if path else None, "tail": ""}
    content = path.read_text(encoding="utf-8").splitlines()
    return {"job_id": job_id, "log_path": str(path), "tail": "\n".join(content[-lines:])}


def cancel_job(cwd: str | Path | None, job_id: str) -> dict[str, Any]:
    state = load_job(cwd, job_id)
    if state.status != "running" or not state.pid:
        return state.to_dict()
    try:
        os.killpg(state.pid, signal.SIGTERM)
        process = _ACTIVE_PROCESSES.pop(job_id, None)
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        state.status = "cancelled"
        state.completed_at = utc_now_iso()
        state.notes.append("Cancellation requested via SIGTERM.")
        save_job(cwd, state)
    except ProcessLookupError:
        state.status = "failed"
        state.error = "Runner process was already gone during cancellation."
        state.completed_at = utc_now_iso()
        save_job(cwd, state)
    return state.to_dict()
