from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_payloads import _planning_payloads_for_prompt, _writer_brief_from_planning
from paperorchestra.engine.refine_iteration import run_refinement_iteration
from paperorchestra.runtime.provider_base import BaseProvider


def refine_current_paper(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    iterations: int = 1,
    require_compile_for_accept: bool = False,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    candidate_only: bool = False,
) -> list[dict[str, Any]]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex or not state.artifacts.latest_review_json:
        raise ContractError("Need paper.full.tex and review.latest.json before refine.")
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)

    accepted_results: list[dict[str, Any]] = []
    for _ in range(iterations):
        run = run_refinement_iteration(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            require_compile_for_accept=require_compile_for_accept,
            candidate_only=candidate_only,
            claim_safe=claim_safe,
            narrative_plan=narrative_plan,
            claim_map=claim_map,
            citation_placement_plan=citation_placement_plan,
            writer_brief=writer_brief,
        )
        accepted_results.append(run.result)
        if run.stop_after:
            break

    return accepted_results
