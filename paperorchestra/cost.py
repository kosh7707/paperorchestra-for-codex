from __future__ import annotations

from pathlib import Path
from typing import Any

from .omx_bridge import _resolve_omx_model, _resolve_omx_reasoning_effort
from .session import load_session


def _file_size(path: str | None) -> int:
    if not path:
        return 0
    candidate = Path(path)
    return candidate.stat().st_size if candidate.exists() else 0


def _approx_tokens(chars: int) -> int:
    return max(1, round(chars / 4)) if chars else 0


def estimate_run_cost(
    cwd: str | Path | None,
    *,
    discovery_mode: str = "model",
    refine_iterations: int = 1,
    compile_paper: bool = False,
    runtime_mode: str = "compatibility",
) -> dict[str, Any]:
    state = load_session(cwd)
    input_paths = {
        "idea": state.inputs.idea_path,
        "experimental_log": state.inputs.experimental_log_path,
        "template": state.inputs.template_path,
        "guidelines": state.inputs.guidelines_path,
    }
    input_chars = sum(_file_size(path) for path in input_paths.values())
    existing_artifact_chars = sum(
        _file_size(path)
        for path in [
            state.artifacts.outline_json,
            state.artifacts.citation_map_json,
            state.artifacts.paper_full_tex,
            state.artifacts.latest_review_json,
        ]
    )

    base_calls = [
        {"stage": "outline", "min_calls": 1, "max_calls": 1},
        {"stage": "plot", "min_calls": 1, "max_calls": 1},
        {
            "stage": "candidate_discovery",
            "min_calls": 1 if discovery_mode == "model" else 0,
            "max_calls": 1 if discovery_mode == "model" else 0,
        },
        {"stage": "intro_related", "min_calls": 1, "max_calls": 2},
        {"stage": "section_writing", "min_calls": 1, "max_calls": 2},
        {"stage": "review", "min_calls": 1, "max_calls": 1},
        {
            "stage": "refinement",
            "min_calls": max(0, refine_iterations) * 2,
            "max_calls": max(0, refine_iterations) * 4,
        },
    ]
    min_calls = sum(item["min_calls"] for item in base_calls)
    max_calls = sum(item["max_calls"] for item in base_calls)

    return {
        "session_id": state.session_id,
        "runtime_mode": runtime_mode,
        "discovery_mode": discovery_mode,
        "refine_iterations": refine_iterations,
        "compile_requested": compile_paper,
        "omx_model": _resolve_omx_model(),
        "omx_reasoning_effort": _resolve_omx_reasoning_effort(),
        "estimated_model_calls": {"min": min_calls, "max": max_calls, "by_stage": base_calls},
        "estimated_external_calls": {
            "semantic_scholar_verification": "one request per candidate when --verify-mode live",
            "search_grounded_discovery": "Semantic Scholar + OpenAlex per query when discovery_mode=search-grounded and PAPERO_SEARCH_GROUNDED_MODE=live",
            "latex_compile": 1 if compile_paper else 0,
        },
        "input_size": {"chars": input_chars, "approx_tokens": _approx_tokens(input_chars)},
        "existing_artifact_context_size": {
            "chars": existing_artifact_chars,
            "approx_tokens": _approx_tokens(existing_artifact_chars),
            "note": "Only currently materialized artifacts are counted; future stage prompts can be larger after citation/plot artifacts are generated.",
        },
        "notes": [
            "This is a rough pre-flight estimate, not provider billing telemetry.",
            "Refinement can add review retries, compile checks, or preservation paths depending on validator and reviewer outcomes.",
        ],
    }
