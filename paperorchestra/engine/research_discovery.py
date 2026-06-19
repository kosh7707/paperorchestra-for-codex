from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.prompt_context import _data_block, _read_inputs
from paperorchestra.engine.schema_research import CANDIDATE_SCHEMA
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.research.literature import build_search_grounded_candidates, search_semantic_scholar
from paperorchestra.runtime.provider_base import BaseProvider


def _outline_search_queries(outline: dict[str, Any]) -> tuple[list[str], int]:
    intro = outline["intro_related_work_plan"].get("introduction_strategy", {})
    related = outline["intro_related_work_plan"].get("related_work_strategy", {})
    queries: list[str] = []
    queries.extend(intro.get("search_directions", []))
    for subsection in related.get("subsections", []):
        mission = subsection.get("sota_investigation_mission")
        if mission:
            queries.append(mission)
        queries.extend(subsection.get("limitation_search_queries", []))
    return queries, len(intro.get("search_directions", []))


def _experimental_log_search_queries(experimental_log_text: str) -> list[str]:
    queries: list[str] = []
    for label in ("Baselines", "Datasets / Benchmarks", "Datasets", "Evaluation Metrics"):
        match = re.search(rf"\*\*\s*{re.escape(label)}\s*:\*\*\s*(.+)", experimental_log_text, re.IGNORECASE)
        if not match:
            continue
        values = [item.strip() for item in re.split(r"[;,]", match.group(1)) if item.strip()]
        queries.extend(values)
    seen: set[str] = set()
    deduped: list[str] = []
    for query in queries:
        normalized = query.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(query)
    return deduped


def _build_candidate_payload(outline: dict[str, Any], state, provider: BaseProvider | None, mode: str, *, runtime_mode: str = "compatibility", cwd: str | Path | None = None) -> tuple[dict[str, Any], str, bool, list[str]]:
    queries, macro_query_count = _outline_search_queries(outline)
    inputs = _read_inputs(state)
    supplemental_queries = _experimental_log_search_queries(inputs["experimental_log"])
    for query in supplemental_queries:
        if query not in queries:
            queries.append(query)
    if mode == "scholar-only":
        macro_candidates = []
        micro_candidates = []
        notes = ["Scholar-only mode used Python discovery."]
        for idx, query in enumerate(queries):
            try:
                papers = search_semantic_scholar(query, limit=3)
            except Exception as exc:
                notes.append(f"Scholar-only query failed for '{query}': {exc}")
                papers = []
            for paper in papers:
                candidate = {
                    "title_guess": paper.get("title", ""),
                    "why_relevant": "Recovered from Semantic Scholar query result.",
                    "origin_query": query,
                    "role_guess": "macro" if idx < macro_query_count else "micro",
                    "discovery_source": "semantic_scholar",
                }
                if candidate["role_guess"] == "macro":
                    macro_candidates.append(candidate)
                else:
                    micro_candidates.append(candidate)
        return {"macro_candidates": macro_candidates, "micro_candidates": micro_candidates}, "python", True, notes

    if mode == "search-grounded":
        grounding_mode = os.environ.get("PAPERO_SEARCH_GROUNDED_MODE")
        if not grounding_mode:
            grounding_mode = "mock" if getattr(provider, "name", None) == "mock" else "live"
        payload, notes = build_search_grounded_candidates(
            queries,
            macro_query_count=macro_query_count,
            cutoff_date=state.inputs.cutoff_date,
            per_source_limit=3,
            mode=grounding_mode,
        )
        return payload, "python", False, notes or [f"Search-grounded substitute used Semantic Scholar + OpenAlex discovery in {grounding_mode} mode."]

    if provider is None:
        raise ContractError("Model discovery mode requires a provider.")
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.discovery_system,
            user_prompt=_discovery_payload_from_outline(outline, state.inputs.cutoff_date),
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="team",
        trace_stage="literature",
        output_schema=CANDIDATE_SCHEMA,
    )
    return extract_json(response), lane_type, fallback_used, lane_notes


def _write_candidate_artifacts(cwd: str | Path | None, payload: dict[str, Any]) -> Path:
    if "macro_candidates" not in payload or "micro_candidates" not in payload:
        raise ContractError("candidate discovery output must contain macro_candidates and micro_candidates")
    path = artifact_path(cwd, "candidate_papers.json")
    write_json(path, payload)
    return path


def _discovery_payload_from_outline(outline: dict[str, Any], cutoff_date: str | None) -> str:
    return _data_block(
        "discovery_payload.json",
        json.dumps(
            {
                "intro_related_work_plan": outline["intro_related_work_plan"],
                "section_plan": outline["section_plan"],
                "cutoff_date": cutoff_date,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
