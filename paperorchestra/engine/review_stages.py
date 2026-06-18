from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, read_json, read_text, write_json
from paperorchestra.core.models import ScoreSnapshot
from paperorchestra.core.session import load_session, review_path, save_session
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
    _lane_owner,
    _provider_name,
    _review_provenance_payload,
)
from paperorchestra.engine.current_manuscript_stages import (
    compile_current_paper,
    record_current_validation_report,
    write_figure_placement_review,
)
from paperorchestra.engine.prompt_context import _compact_citation_map_for_prompt, _data_block, _prompt_compact_text
from paperorchestra.engine.schemas import REVIEW_SCHEMA
from paperorchestra.manuscript.citations import canonical_citation_keys
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def review_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    review_name: str = "review.latest.json",
    runtime_mode: str = "compatibility",
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before review.")
    paper_text = read_text(state.artifacts.paper_full_tex)
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_paper_text = _prompt_compact_text(paper_text, head_chars=22000, tail_chars=4000)
    prompt_citation_map = _compact_citation_map_for_prompt(
        citation_map,
        include_abstract=False,
        include_authors=False,
        include_year=False,
        include_venue=False,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    user_prompt = f"""
{_data_block('paper.tex', prompt_paper_text)}

{_data_block('citation_map.json', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    avg_citation_count = max(1, len(canonical_citation_keys(citation_map)))
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=PROMPTS.render_review_system(avg_citation_count=avg_citation_count), user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="reviewer",
        trace_stage="review",
        output_schema=REVIEW_SCHEMA,
            )
    payload = extract_json(response)
    payload.setdefault("schema_version", "paper-review/1")
    payload["manuscript_path"] = state.artifacts.paper_full_tex
    manuscript_sha = hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
    payload["manuscript_sha256"] = manuscript_sha
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
    )
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)
    path = review_path(cwd, review_name)
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="review",
        role="Reviewer Lane",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.paper_full_tex or ""],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    payload["review_provenance"] = _review_provenance_payload(
        cwd,
        stage="review",
        manuscript_sha256=manuscript_sha,
        lane_manifest_path=lane_path,
    )
    write_json(path, payload)
    state.artifacts.latest_review_json = str(path)
    score = float(payload.get("overall_score", 0.0))
    axes = _extract_axis_scores(payload)
    state.review_history.append(ScoreSnapshot(overall_score=score, raw_path=str(path), axes=axes))
    state.active_artifact = review_name
    state.notes.append(f"Paper reviewed: overall_score={score}")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path


def _extract_axis_scores(review_payload: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    axis_scores = review_payload.get("axis_scores", {})
    if isinstance(axis_scores, dict):
        for key, value in axis_scores.items():
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                result[key] = float(value["score"])
            elif isinstance(value, (int, float)):
                result[key] = float(value)
    return result

