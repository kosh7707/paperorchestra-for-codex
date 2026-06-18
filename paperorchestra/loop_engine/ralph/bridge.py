from __future__ import annotations

import sys
from pathlib import Path

from paperorchestra.core.models import utc_now_iso
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS
from paperorchestra.loop_engine.ralph.action_dispatch import dispatch_qa_loop_actions
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext
from paperorchestra.loop_engine.ralph.bridge_candidate_flow import resolve_post_dispatch_candidate
from paperorchestra.loop_engine.ralph.bridge_lifecycle import (
    finish_execution_error,
    finish_no_supported_actions,
    finish_successful_step,
    finish_terminal_noop,
    record_unsupported_actions,
)
from paperorchestra.loop_engine.ralph.bridge_post_action import verify_after_qa_loop_actions
from paperorchestra.loop_engine.ralph.bridge_preflight import prepare_qa_loop_preflight
from paperorchestra.loop_engine.ralph.bridge_rollback import (
    capture_qa_loop_rollback_context,
    restore_candidate_after_exception,
)
from paperorchestra.loop_engine.ralph.bridge_runner import QaLoopStepRunner
from paperorchestra.loop_engine.ralph.candidate_outcomes import should_override_no_progress
from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.provider_registry import get_citation_support_provider
from .state import (
    TERMINAL_VERDICTS,
    StepResult,
    recover_pending_manuscript_write,
)


def run_qa_loop_step(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    require_compile: bool = False,
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
    quality_eval_input_path: str | Path | None = None,
    qa_loop_plan_input_path: str | Path | None = None,
    citation_support_review_path: str | Path | None = None,
) -> StepResult:
    return QaLoopStepRunner(
        cwd=cwd,
        provider=provider,
        stage=sys.modules[__name__],
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        runtime_mode=runtime_mode,
        require_compile=require_compile,
        citation_evidence_mode=citation_evidence_mode,
        citation_provider_name=citation_provider_name,
        citation_provider_command=citation_provider_command,
        quality_eval_input_path=quality_eval_input_path,
        qa_loop_plan_input_path=qa_loop_plan_input_path,
        citation_support_review_path=citation_support_review_path,
    ).run()


__all__ = ["QaLoopStepRunner", "run_qa_loop_step"]
