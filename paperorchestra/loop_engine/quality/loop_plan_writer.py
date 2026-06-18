from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, save_session
from paperorchestra.loop_engine.quality.audit_snapshots import refresh_quality_audit_artifacts
from paperorchestra.loop_engine.quality.eval import build_quality_eval
from paperorchestra.loop_engine.quality.eval_input import validate_quality_eval_input as _validate_quality_eval_input
from paperorchestra.loop_engine.quality.history_writer import append_quality_loop_history
from paperorchestra.loop_engine.quality.loop_plan_builder import build_quality_loop_plan
from paperorchestra.loop_engine.quality.policy import DEFAULT_MAX_ITERATIONS


def write_quality_loop_plan(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    accept_mixed_provenance: bool = False,
    quality_eval_input_path: str | Path | None = None,
    append_history: bool = True,
) -> tuple[Path, dict[str, Any]]:
    state, reproducibility_payload, fidelity_payload = refresh_quality_audit_artifacts(
        cwd,
        require_live_verification=require_live_verification,
    )
    quality_eval, quality_eval_path = _quality_eval_for_plan_write(
        cwd=cwd,
        state=state,
        reproducibility_payload=reproducibility_payload,
        fidelity_payload=fidelity_payload,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        quality_eval_input_path=quality_eval_input_path,
    )
    payload = build_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval=quality_eval,
        quality_eval_path=quality_eval_path,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "qa-loop.plan.json")
    write_json(path, payload)
    if append_history:
        append_quality_loop_history(
            cwd,
            quality_eval,
            verdict=payload.get("verdict"),
            plan_path=path,
            quality_eval_path=quality_eval_path,
            event_type="qa_loop_plan",
            consumes_budget=False,
        )
    state.notes.append(f"QA loop plan recorded: {path.name}")
    save_session(cwd, state)
    return path, payload


def _quality_eval_for_plan_write(
    *,
    cwd: str | Path | None,
    state: Any,
    reproducibility_payload: dict[str, Any],
    fidelity_payload: dict[str, Any],
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    quality_eval_input_path: str | Path | None,
) -> tuple[dict[str, Any], Path]:
    if quality_eval_input_path:
        quality_eval_path = Path(quality_eval_input_path).resolve()
        loaded_quality_eval = read_json(quality_eval_path)
        if not isinstance(loaded_quality_eval, dict):
            raise ValueError(f"quality-eval input is not a JSON object: {quality_eval_path}")
        _validate_quality_eval_input(
            loaded_quality_eval,
            state=state,
            reproducibility=reproducibility_payload,
            fidelity=fidelity_payload,
            quality_eval_path=quality_eval_path,
        )
        return loaded_quality_eval, quality_eval_path
    quality_eval = build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility_payload,
        fidelity=fidelity_payload,
    )
    quality_eval_path = artifact_path(cwd, "quality-eval.json")
    write_json(quality_eval_path, quality_eval)
    return quality_eval, quality_eval_path
