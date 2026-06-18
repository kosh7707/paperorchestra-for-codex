from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.narrative_artifacts import require_fresh_planning_artifacts


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
