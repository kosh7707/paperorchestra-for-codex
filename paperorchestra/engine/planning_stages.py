from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import assert_author_facing_payload, normalized_claim_projection, sanitize_author_facing_text
from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _lane_owner
from paperorchestra.engine.prompt_context import (
    _compact_outline_for_prompt,
    _data_block,
    _prompt_compact_text,
    _read_inputs,
)
from paperorchestra.engine.schemas import OUTLINE_SCHEMA, normalize_outline_payload, validate_outline
from paperorchestra.manuscript.narrative_artifacts import require_fresh_planning_artifacts, write_planning_artifacts
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def _append_unique_note(state, note: str, *, dedupe_window: int = 5) -> bool:
    if not note:
        return False
    if note in state.notes[-dedupe_window:]:
        return False
    state.notes.append(note)
    return True


def plan_narrative_and_claims(
    cwd: str | Path | None,
    provider: BaseProvider | None = None,
    *,
    runtime_mode: str = "compatibility",
) -> dict[str, Path]:
    state = load_session(cwd)
    paths = write_planning_artifacts(cwd)
    lane_path = record_lane_manifest(
        cwd,
        stage="narrative_planning",
        role="Narrative Claim Planner",
        runtime_mode=runtime_mode,
        lane_type="ralph",
        owner="paperorchestra",
        status="completed",
        input_artifacts=[
            state.artifacts.outline_json or "",
            state.artifacts.citation_map_json or "",
            state.artifacts.references_bib or "",
            state.inputs.idea_path,
            state.inputs.experimental_log_path,
            state.inputs.template_path,
        ],
        output_artifacts=[str(path) for path in paths.values()],
        fallback_used=False,
        notes=["Deterministic conservative narrative/claim/citation placement planning artifacts recorded."],
    )
    state = load_session(cwd)
    state.current_phase = "narrative_planning"
    state.active_artifact = "narrative_plan.json"
    _append_unique_note(state, "Plot and literature completed in parallel before narrative planning.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return paths


def _planning_payloads_for_prompt(cwd: str | Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = load_session(cwd)
    try:
        require_fresh_planning_artifacts(cwd)
    except RuntimeError as exc:
        raise ContractError(str(exc)) from exc
    narrative = read_json(state.artifacts.narrative_plan_json) if state.artifacts.narrative_plan_json else {}
    claim_map = read_json(state.artifacts.claim_map_json) if state.artifacts.claim_map_json else {}
    citation_plan = read_json(state.artifacts.citation_placement_plan_json) if state.artifacts.citation_placement_plan_json else {}
    return narrative, claim_map, citation_plan


def _filter_planning_payloads_for_sections(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    section_names: list[str] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not section_names:
        return narrative_plan, claim_map, citation_placement_plan
    wanted = {name.strip().lower() for name in section_names if name.strip()}
    claims = [
        claim
        for claim in claim_map.get("claims", [])
        if isinstance(claim, dict) and str(claim.get("target_section") or "").strip().lower() in wanted
    ]
    claim_ids = {str(claim.get("id")) for claim in claims}
    narrative = dict(narrative_plan)
    narrative["section_roles"] = [
        role
        for role in narrative_plan.get("section_roles", [])
        if isinstance(role, dict) and str(role.get("section_title") or "").strip().lower() in wanted
    ]
    narrative["story_beats"] = [
        beat
        for beat in narrative_plan.get("story_beats", [])
        if isinstance(beat, dict) and str(beat.get("target_section") or "").strip().lower() in wanted
    ]
    claim_payload = dict(claim_map)
    claim_payload["claims"] = claims
    citation_payload = dict(citation_placement_plan)
    citation_payload["placements"] = [
        placement
        for placement in citation_placement_plan.get("placements", [])
        if isinstance(placement, dict)
        and (
            str(placement.get("target_section") or "").strip().lower() in wanted
            or str(placement.get("claim_id") or "") in claim_ids
        )
    ]
    return narrative, claim_payload, citation_payload


def _writer_brief_from_planning(
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project planning artifacts into an author-facing prose brief.

    Raw planning artifacts contain IDs, provenance hashes, source references,
    and machine-control labels. Those are useful for validators but too easy
    for a prose model to copy into the manuscript. The writer brief consumes
    the shared normalized boundary projection and keeps only scholarly,
    author-facing obligations.
    """
    claims_by_section: dict[str, list[dict[str, Any]]] = {}

    def _safe_supporting_evidence(claim: dict[str, Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for anchor in claim.get("evidence_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            excerpt = sanitize_author_facing_text(
                str(anchor.get("evidence_excerpt") or anchor.get("excerpt") or ""),
                fallback="",
            )
            if not excerpt:
                continue
            item: dict[str, Any] = {
                "excerpt": _prompt_compact_text(excerpt, head_chars=360, tail_chars=0),
            }
            line_start = anchor.get("line_start")
            line_end = anchor.get("line_end")
            if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0 and line_end >= line_start:
                item["location"] = f"lines {line_start}-{line_end}"
            evidence.append(item)
        legacy_excerpt = sanitize_author_facing_text(str(claim.get("excerpt") or ""), fallback="")
        if legacy_excerpt and not evidence:
            evidence.append({"excerpt": _prompt_compact_text(legacy_excerpt, head_chars=360, tail_chars=0)})
        return evidence

    for claim in claim_map.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        projection = normalized_claim_projection(claim)
        section = str(projection.get("target_section") or "").strip() or "Unassigned"
        grounding = str(projection.get("grounding") or "").strip()
        grounding_label = {
            "source_material": "technical_evidence",
            "experimental_log": "measurement_log",
            "human_boundary": "author_scope_constraints",
            "verified_citation": "verified_background_literature",
        }.get(grounding, grounding or None)
        supporting_evidence = _safe_supporting_evidence(claim)
        claims_by_section.setdefault(section, []).append(
            {
                "claim": _prompt_compact_text(str(projection.get("authorial_claim") or ""), head_chars=260, tail_chars=0),
                "type": projection.get("claim_type"),
                "grounding": grounding_label,
                "required": bool(projection.get("required", True)),
                "risk": projection.get("risk"),
                "supporting_evidence": supporting_evidence,
                "supporting_excerpt": supporting_evidence[0]["excerpt"] if supporting_evidence else "",
                "coverage_terms": projection.get("coverage_groups") or [],
            }
        )
    citation_guidance: list[dict[str, Any]] = []
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        citation_guidance.append(
            {
                "section": placement.get("target_section"),
                "citation_keys": placement.get("citation_keys") or [],
                "purpose": _prompt_compact_text(str(placement.get("purpose") or placement.get("rationale") or ""), head_chars=220, tail_chars=0),
            }
        )
    section_roles = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "").strip()
        must_cover = [str(item) for item in role.get("must_cover") or [] if str(item).strip()]
        required_claims = claims_by_section.get(title, [])
        if required_claims:
            must_cover = [claim["claim"] for claim in required_claims if claim.get("claim")]
        section_roles.append(
            {
                "section": title,
                "role": _prompt_compact_text(
                    sanitize_author_facing_text(str(role.get("role") or ""), fallback="Develop this section from stated evidence, assumptions, and assigned citations."),
                    head_chars=260,
                    tail_chars=0,
                ),
                "must_cover": must_cover,
                "must_not_claim": role.get("must_not_claim") or [],
                "required_claims": required_claims,
            }
        )
    brief = {
        "thesis": _prompt_compact_text(
            sanitize_author_facing_text(
                str(narrative_plan.get("thesis") or ""),
                fallback="Build a coherent scholarly draft that preserves the paper's stated claims, scope, and citation positioning.",
            ),
            head_chars=500,
            tail_chars=0,
        ),
        "contribution_boundary": [
            sanitize_author_facing_text(str(item), fallback="State evidence limits as ordinary scholarly assumptions, scope, and limitations.")
            for item in (narrative_plan.get("contribution_boundary") or [])
            if str(item).strip()
        ],
        "section_roles": section_roles,
        "citation_guidance": citation_guidance,
        "authoring_rules": [
            "Write only scholarly paper prose.",
            "Use external citations for background, standards, baselines, and contrast; keep core method, proof, and result claims tied to technical evidence.",
            "State limitations as normal scholarly scope conditions rather than process disclaimers.",
        ],
    }
    _validate_author_facing_writer_brief(brief)
    return brief


def _validate_author_facing_writer_brief(brief: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_author_facing_payload(brief, label="author_facing_writer_brief.json")
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return brief


def _author_facing_writer_brief_block(brief: dict[str, Any]) -> str:
    return _data_block(
        "scholarly_authoring_brief",
        json.dumps(_validate_author_facing_writer_brief(brief), indent=2, ensure_ascii=False),
    )


def generate_outline(cwd: str | Path | None, provider: BaseProvider, *, runtime_mode: str = "compatibility") -> Path:
    state = load_session(cwd)
    inputs = _read_inputs(state)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=8000, tail_chars=1500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=9000, tail_chars=2500)
    prompt_template = _prompt_compact_text(inputs["template"], head_chars=9000, tail_chars=1000)
    user_prompt = f"""
Inputs:
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

