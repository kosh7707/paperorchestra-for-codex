from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_payload_filters import _filter_planning_payloads_for_sections
from paperorchestra.engine.writer_brief_builder import _writer_brief_from_planning
from paperorchestra.manuscript.narrative_artifacts import require_fresh_planning_artifacts
from paperorchestra.engine.writer_brief_claims import (
    _claims_by_section_for_writer_brief,
    _safe_supporting_evidence,
)
from paperorchestra.engine.writer_brief_guidance import _citation_guidance_for_writer_brief
from paperorchestra.engine.writer_brief_sections import _section_roles_for_writer_brief
from paperorchestra.engine.writer_brief_validation import _author_facing_writer_brief_block, _validate_author_facing_writer_brief


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

__all__ = [
    "_author_facing_writer_brief_block",
    "_citation_guidance_for_writer_brief",
    "_claims_by_section_for_writer_brief",
    "_filter_planning_payloads_for_sections",
    "_planning_payloads_for_prompt",
    "_safe_supporting_evidence",
    "_section_roles_for_writer_brief",
    "_validate_author_facing_writer_brief",
    "_writer_brief_from_planning",
]
