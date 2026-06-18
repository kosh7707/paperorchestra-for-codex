from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, save_session
from paperorchestra.loop_engine.quality.audit_snapshots import refresh_quality_audit_artifacts
from paperorchestra.loop_engine.quality.eval import build_quality_eval
from paperorchestra.loop_engine.quality.history_writer import append_quality_loop_history
from paperorchestra.loop_engine.quality.policy import DEFAULT_MAX_ITERATIONS


def write_quality_eval(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    append_history: bool = False,
    current_attempt_consumes_budget: bool = False,
) -> tuple[Path, dict[str, Any]]:
    state, reproducibility_payload, fidelity_payload = refresh_quality_audit_artifacts(
        cwd,
        require_live_verification=require_live_verification,
    )
    payload = build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility_payload,
        fidelity=fidelity_payload,
        current_attempt_consumes_budget=current_attempt_consumes_budget,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "quality-eval.json")
    write_json(path, payload)
    state.notes.append(f"Quality eval recorded: {path.name}")
    save_session(cwd, state)
    if append_history:
        append_quality_loop_history(cwd, payload, quality_eval_path=path, event_type="quality_eval", consumes_budget=False)
    return path, payload
