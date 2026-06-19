from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import extract_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion_env import _build_completion_request
from paperorchestra.engine.completion_identity import _lane_owner
from paperorchestra.engine.completion_runtime import _complete_with_runtime_mode
from paperorchestra.engine.plan_gate import approved_plan_path
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text, _read_inputs
from paperorchestra.engine.schema_outline import OUTLINE_SCHEMA, normalize_outline_payload, validate_outline
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def generate_outline(cwd: str | Path | None, provider: BaseProvider, *, runtime_mode: str = "compatibility") -> Path:
    state = load_session(cwd)
    inputs = _read_inputs(state)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=8000, tail_chars=1500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=9000, tail_chars=2500)
    prompt_template = _prompt_compact_text(inputs["template"], head_chars=9000, tail_chars=1000)
    plan_path = approved_plan_path(cwd)
    prompt_plan = (
        _prompt_compact_text(plan_path.read_text(encoding="utf-8"), head_chars=9000, tail_chars=1500)
        if plan_path is not None
        else "No author-approved paper-plan.md was found for this outline run."
    )
    user_prompt = f"""
Inputs:
{_data_block('paper-plan.md', prompt_plan)}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('template.tex', prompt_template)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}

Manuscript prose hygiene:
- Write only manuscript-facing scholarly prose.
- Express evidence limits only as normal scholarly assumptions, scope, and limitations.
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_outline_system(cutoff_date=state.inputs.cutoff_date),
            user_prompt=user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="outline",
        output_schema=OUTLINE_SCHEMA,
    )
    payload = normalize_outline_payload(extract_json(response))
    validate_outline(payload)
    path = artifact_path(cwd, "outline.json")
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="outline",
        role="Outline Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[
            state.inputs.idea_path,
            state.inputs.experimental_log_path,
            state.inputs.template_path,
            state.inputs.guidelines_path,
            str(plan_path) if plan_path is not None else "",
        ],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.outline_json = str(path)
    state.current_phase = "plot_generation_and_literature_review"
    state.active_artifact = "outline.json"
    state.notes.append("Outline generated.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path
