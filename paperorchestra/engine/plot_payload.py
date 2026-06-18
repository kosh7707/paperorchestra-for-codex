from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import extract_json
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text, _read_inputs
from paperorchestra.engine.schemas import PLOT_SCHEMA
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.provider_base import BaseProvider


def _fallback_plot_manifest(outline: dict[str, Any]) -> dict[str, Any]:
    figures = []
    for plot in outline.get("plotting_plan", []):
        figures.append(
            {
                "figure_id": plot["figure_id"],
                "title": plot["title"],
                "plot_type": plot["plot_type"],
                "data_source": plot["data_source"],
                "objective": plot["objective"],
                "aspect_ratio": plot["aspect_ratio"],
                "rendering_brief": plot["objective"],
                "caption": plot["title"],
                "source_fidelity_notes": f"{plot['data_source']}: fallback manifest without model-authored caption.",
            }
        )
    return {"figures": figures}


def _build_plot_payload(
    outline: dict[str, Any],
    state,
    provider: BaseProvider | None,
    *,
    runtime_mode: str = "compatibility",
    cwd: str | Path | None = None,
) -> tuple[dict[str, Any], str, bool, list[str]]:
    inputs = _read_inputs(state)
    if provider is None:
        return _fallback_plot_manifest(outline), "python", True, ["No provider available; fallback manifest used."]
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=5000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=12000, tail_chars=3000)
    user_prompt = f"""
{_data_block('plotting_plan', json.dumps(outline['plotting_plan'], indent=2, ensure_ascii=False))}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}
""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.plot_system, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="team",
        trace_stage="plot",
        output_schema=PLOT_SCHEMA,
    )
    return extract_json(response), lane_type, fallback_used, lane_notes
