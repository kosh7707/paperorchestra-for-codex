from __future__ import annotations

from pathlib import Path

from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.intro_related_draft import IntroRelatedDraft, draft_from_intro_related_response
from paperorchestra.engine.intro_related_prompt import IntroRelatedPromptPlan
from paperorchestra.engine.intro_related_repair import (
    append_initial_intro_related_notes,
    bridge_intro_related_citation_coverage,
    repair_intro_related_draft,
)
from paperorchestra.runtime.provider_base import BaseProvider


def _generate_intro_related_draft(
    cwd: str | Path | None,
    provider: BaseProvider,
    plan: IntroRelatedPromptPlan,
    *,
    runtime_mode: str,
) -> IntroRelatedDraft:
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=plan.system_prompt,
            user_prompt=plan.user_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="intro_related",
    )
    return draft_from_intro_related_response(
        response,
        lane_type=lane_type,
        fallback_used=fallback_used,
        lane_notes=lane_notes,
        plan=plan,
    )


def build_intro_related_draft(
    cwd: str | Path | None,
    provider: BaseProvider,
    plan: IntroRelatedPromptPlan,
    *,
    runtime_mode: str,
) -> IntroRelatedDraft:
    draft = _generate_intro_related_draft(cwd, provider, plan, runtime_mode=runtime_mode)
    draft = repair_intro_related_draft(cwd, provider, plan, draft, runtime_mode=runtime_mode)
    draft = append_initial_intro_related_notes(plan, draft)
    return bridge_intro_related_citation_coverage(draft, plan)
