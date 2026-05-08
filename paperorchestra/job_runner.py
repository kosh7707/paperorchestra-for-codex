from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import traceback

from .jobs import JobState
from .providers import get_provider
from .pipeline import run_pipeline
from .models import utc_now_iso
from .io_utils import write_json


def _save_state(path: Path, state: JobState) -> None:
    state.updated_at = utc_now_iso()
    write_json(path, state.to_dict())


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 4:
        print("usage: python -m paperorchestra.job_runner <spec.json> <log.txt> <result.json> <state.json>", file=sys.stderr)
        return 2
    spec_path = Path(args[0])
    log_path = Path(args[1])
    result_path = Path(args[2])
    state_path = Path(args[3])

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    state = JobState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
    state.status = "running"
    state.started_at = state.started_at or utc_now_iso()
    _save_state(state_path, state)

    try:
        if spec["kind"] != "run_pipeline":
            raise ValueError(f"Unsupported background job kind: {spec['kind']}")

        _append_log(log_path, json.dumps({"job_id": state.job_id, "event": "runner_started", "cwd": spec["cwd"]}, ensure_ascii=False))
        provider = get_provider(spec.get("provider", "mock"), command=spec.get("provider_command"))
        result = run_pipeline(
            spec["cwd"],
            provider=provider,
            discovery_mode=spec.get("discovery_mode", "model"),
            verify_mode=spec.get("verify_mode", "live"),
            verify_error_policy=spec.get("verify_error_policy", "skip"),
            verify_fallback_mode=spec.get("verify_fallback_mode", "none"),
            require_live_verification=bool(spec.get("require_live_verification", False)),
            refine_iterations=int(spec.get("refine_iterations", 1)),
            compile_paper=bool(spec.get("compile_paper", False)),
            runtime_mode=spec.get("runtime_mode", "compatibility"),
        )
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _append_log(log_path, json.dumps({"job_id": state.job_id, "event": "runner_succeeded", "result_status": result.get("status")}, ensure_ascii=False))
        print(json.dumps({"job_id": state.job_id, "status": "succeeded", "result_path": str(result_path)}, ensure_ascii=False))
        state.status = "succeeded"
        state.return_code = 0
        state.completed_at = utc_now_iso()
        _save_state(state_path, state)
        return 0
    except Exception as exc:  # pragma: no cover - process boundary
        traceback.print_exc()
        _append_log(log_path, f"job_runner_error: {exc}")
        state.status = "failed"
        state.error = str(exc)
        state.return_code = 1
        state.completed_at = utc_now_iso()
        _save_state(state_path, state)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
