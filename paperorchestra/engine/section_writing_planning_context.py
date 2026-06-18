from __future__ import annotations

from pathlib import Path

from paperorchestra.engine.planning_payloads import (
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.section_writing_types import PlanningPromptPayloads


def _planning_payloads(cwd: str | Path | None, selected_sections: list[str]) -> PlanningPromptPayloads:
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        selected_sections,
    )
    return PlanningPromptPayloads(
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
        writer_brief=_writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan),
    )
