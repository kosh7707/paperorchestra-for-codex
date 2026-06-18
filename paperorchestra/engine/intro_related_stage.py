from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import load_session
from paperorchestra.engine.intro_related_generation import build_intro_related_draft
from paperorchestra.engine.intro_related_persistence import persist_intro_related_outputs
from paperorchestra.engine.intro_related_prompt import build_intro_related_prompt_plan
from paperorchestra.runtime.provider_base import BaseProvider


def write_intro_related(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    runtime_mode: str = "compatibility",
    claim_safe: bool = False,
    allow_recoverable_contract_issues: bool = False,
) -> Path:
    state = load_session(cwd)
    plan = build_intro_related_prompt_plan(cwd, state, claim_safe=claim_safe)
    draft = build_intro_related_draft(cwd, provider, plan, runtime_mode=runtime_mode)
    return persist_intro_related_outputs(
        cwd,
        state,
        provider,
        draft,
        runtime_mode=runtime_mode,
        allow_recoverable_contract_issues=allow_recoverable_contract_issues,
    )
