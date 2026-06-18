from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.models import SessionState
from paperorchestra.engine.citation_coverage import _citation_coverage_target
from paperorchestra.engine.planning_stages import (
    _author_facing_writer_brief_block,
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _compact_intro_related_plan_for_prompt,
    _data_block,
    _prompt_compact_text,
    _raise_if_strict_source_citations_unmapped,
    _read_inputs,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
)
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.validator import canonical_citation_keys

INTRO_RELATED_SECTIONS = ["Introduction", "Related Work"]


@dataclass(frozen=True)
class IntroRelatedPromptPlan:
    user_prompt: str
    system_prompt: str
    inputs: dict[str, str]
    citation_map: dict[str, Any]
    min_citation_coverage: int
    narrative_plan: dict[str, Any]
    claim_map: dict[str, Any]
    citation_placement_plan: dict[str, Any]
    strict_claim_safe_prompt: bool


def build_intro_related_prompt_plan(
    cwd: str | Path | None,
    state: SessionState,
    *,
    claim_safe: bool,
) -> IntroRelatedPromptPlan:
    if not state.artifacts.outline_json or not state.artifacts.citation_map_json:
        raise ContractError("Need outline.json and citation_map.json before writing intro/related work.")

    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        INTRO_RELATED_SECTIONS,
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)

    outline = read_json(state.artifacts.outline_json)
    citation_map = read_json(state.artifacts.citation_map_json)
    citation_keys = canonical_citation_keys(citation_map)
    min_citation_coverage = _citation_coverage_target(citation_map)
    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="intro_related",
        strict_claim_safe=strict_claim_safe_prompt,
    )

    prompt_intro_related_plan = _compact_intro_related_plan_for_prompt(outline["intro_related_work_plan"])
    prompt_citation_map = _compact_citation_map_for_prompt(
        citation_map,
        include_abstract=strict_claim_safe_prompt,
        include_authors=False,
        include_year=strict_claim_safe_prompt,
        include_venue=strict_claim_safe_prompt,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    source_critical_context = _source_critical_context_for_prompt(inputs)
    user_prompt = f"""
{_data_block('template.tex', _prompt_compact_text(inputs['template'], head_chars=5000, tail_chars=500))}

{_data_block('intro_related_authoring_plan', json.dumps(prompt_intro_related_plan, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('project_idea', _prompt_compact_text(inputs['idea'], head_chars=4000, tail_chars=500))}

{_data_block(
    'project_experimental_log',
    _prompt_compact_text(inputs['experimental_log'], head_chars=7000, tail_chars=1500),
)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_checklist', json.dumps(sorted(citation_keys), indent=2, ensure_ascii=False))}

{_data_block('collected_papers', json.dumps(prompt_citation_map, indent=2, ensure_ascii=False))}

{_data_block('paper_count', str(len(citation_keys)))}

{_data_block('min_cite_paper_count', str(min_citation_coverage))}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}
""".strip()
    return IntroRelatedPromptPlan(
        user_prompt=user_prompt,
        system_prompt=PROMPTS.render_intro_related_system(
            paper_count=len(citation_keys),
            min_cite_paper_count=min_citation_coverage,
            cutoff_date=state.inputs.cutoff_date,
        ),
        inputs=inputs,
        citation_map=citation_map,
        min_citation_coverage=min_citation_coverage,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
    )
