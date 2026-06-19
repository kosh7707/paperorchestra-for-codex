from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session, save_session
from paperorchestra.engine.completion_identity import _provider_name
from paperorchestra.engine.intro_related_stage import write_intro_related
from paperorchestra.engine.pipeline_runner import PipelineRun
from paperorchestra.engine.planning_stages import generate_outline, plan_narrative_and_claims
from paperorchestra.engine.plot_stages import run_parallel_plot_and_literature
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.reports import record_compile_environment_report, record_fidelity_report
from paperorchestra.engine.research_verification_stage import build_bib, verify_papers
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.reviews.reproducibility import write_reproducibility_audit
from paperorchestra.runtime.parity import record_runtime_parity_report
from paperorchestra.runtime.provider_base import BaseProvider


def _emit_stage_event(stage: str, event: str, **payload: Any) -> None:
    record = {"stage": stage, "event": event}
    record.update(payload)
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr)


def run_pipeline(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    discovery_mode: str = "model",
    verify_mode: str = "live",
    verify_error_policy: str = "skip",
    verify_fallback_mode: str = "none",
    require_live_verification: bool = False,
    refine_iterations: int = 1,
    compile_paper: bool = False,
    runtime_mode: str = "compatibility",
) -> dict[str, Any]:
    return PipelineRun(
        cwd=cwd,
        provider=provider,
        stage=sys.modules[__name__],
        discovery_mode=discovery_mode,
        verify_mode=verify_mode,
        verify_error_policy=verify_error_policy,
        verify_fallback_mode=verify_fallback_mode,
        require_live_verification=require_live_verification,
        refine_iterations=refine_iterations,
        compile_paper=compile_paper,
        runtime_mode=runtime_mode,
    ).run()


__all__ = ["ContractError", "PipelineRun", "run_pipeline"]
