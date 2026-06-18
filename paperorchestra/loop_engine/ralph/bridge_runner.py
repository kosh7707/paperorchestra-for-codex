from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS
from paperorchestra.runtime.provider_base import BaseProvider


@dataclass
class QaLoopStepRunner:
    cwd: str | Path | None
    provider: BaseProvider
    stage: Any
    quality_mode: str = "claim_safe"
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    require_live_verification: bool = False
    accept_mixed_provenance: bool = False
    runtime_mode: str = "compatibility"
    require_compile: bool = False
    citation_evidence_mode: str = "web"
    citation_provider_name: str | None = None
    citation_provider_command: str | None = None
    quality_eval_input_path: str | Path | None = None
    qa_loop_plan_input_path: str | Path | None = None
    citation_support_review_path: str | Path | None = None

    def run(self):
        self.stage.recover_pending_manuscript_write(self.cwd)
        preflight = self._prepare_preflight()
        execution = preflight.execution
        if preflight.initial_verdict in self.stage.TERMINAL_VERDICTS:
            return self.stage.finish_terminal_noop(self.cwd, execution, preflight.initial_verdict)

        self.stage.record_unsupported_actions(execution, preflight.unsupported_actions)
        if not preflight.actions:
            return self.stage.finish_no_supported_actions(self.cwd, execution)

        rollback = self.stage.capture_qa_loop_rollback_context(self.cwd)
        citation_provider = self._citation_provider()
        dispatch_result = self._dispatch(preflight, execution, rollback, citation_provider)
        try:
            post_action = self._verify_after_actions(preflight, execution, citation_provider)
            resolved = self._resolve_candidate(preflight, rollback, dispatch_result, execution, post_action)
            verdict = self._final_verdict(resolved, execution, dispatch_result, post_action)
        except Exception as exc:
            return self._finish_exception(preflight, execution, rollback, dispatch_result, exc)

        return self.stage.finish_successful_step(
            cwd=self.cwd,
            execution=execution,
            final_eval=resolved.final_eval,
            final_eval_path=resolved.final_eval_path,
            final_plan_path=resolved.final_plan_path,
            final_summary=resolved.final_summary,
            final_progress=resolved.final_progress,
            final_verification=resolved.final_verification,
            verdict=verdict,
        )

    def _prepare_preflight(self):
        return self.stage.prepare_qa_loop_preflight(
            cwd=self.cwd,
            started_at=self.stage.utc_now_iso(),
            require_live_verification=self.require_live_verification,
            quality_mode=self.quality_mode,
            max_iterations=self.max_iterations,
            accept_mixed_provenance=self.accept_mixed_provenance,
            quality_eval_input_path=self.quality_eval_input_path,
            qa_loop_plan_input_path=self.qa_loop_plan_input_path,
            citation_support_review_path=self.citation_support_review_path,
        )

    def _citation_provider(self):
        name = self.citation_provider_name or (
            "shell" if self.citation_evidence_mode in {"web", "model"} else "mock"
        )
        return self.stage.get_citation_support_provider(
            name,
            command=self.citation_provider_command,
            evidence_mode=self.citation_evidence_mode,
        )

    def _dispatch(self, preflight, execution, rollback, citation_provider):
        return self.stage.dispatch_qa_loop_actions(
            preflight.actions,
            execution,
            self.stage.QaLoopActionDispatchContext(
                cwd=self.cwd,
                provider=self.provider,
                runtime_mode=self.runtime_mode,
                require_compile=self.require_compile,
                quality_mode=self.quality_mode,
                citation_evidence_mode=self.citation_evidence_mode,
                citation_provider=citation_provider,
                paper_path=rollback.paper_path,
                original_paper=rollback.original_paper,
            ),
        )

    def _verify_after_actions(self, preflight, execution, citation_provider):
        return self.stage.verify_after_qa_loop_actions(
            cwd=self.cwd,
            before_eval=preflight.before_eval,
            before_summary=preflight.before_summary,
            execution=execution,
            citation_provider=citation_provider,
            citation_evidence_mode=self.citation_evidence_mode,
            quality_mode=self.quality_mode,
            max_iterations=self.max_iterations,
            require_live_verification=self.require_live_verification,
            accept_mixed_provenance=self.accept_mixed_provenance,
            require_compile=self.require_compile,
        )

    def _resolve_candidate(self, preflight, rollback, dispatch_result, execution, post_action):
        resolved = self.stage.resolve_post_dispatch_candidate(
            cwd=self.cwd,
            rollback=rollback,
            require_compile=self.require_compile,
            require_live_verification=self.require_live_verification,
            quality_mode=self.quality_mode,
            max_iterations=self.max_iterations,
            accept_mixed_provenance=self.accept_mixed_provenance,
            before_eval=preflight.before_eval,
            before_summary=preflight.before_summary,
            actions_attempted=bool(execution["actions_attempted"]),
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
            citation_candidate_path=dispatch_result.citation_candidate_path,
            post_action=post_action,
        )
        execution.update(resolved.execution_updates)
        return resolved

    def _final_verdict(self, resolved, execution, dispatch_result, post_action) -> str:
        verdict = resolved.verdict
        if self.stage.should_override_no_progress(
            verdict=verdict,
            actions_attempted=execution["actions_attempted"],
            final_progress=resolved.final_progress,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
            candidate_progress=post_action.progress,
        ):
            execution["no_progress_override"] = True
            return "human_needed"
        return verdict

    def _finish_exception(self, preflight, execution, rollback, dispatch_result, exc: Exception):
        self.stage.restore_candidate_after_exception(
            cwd=self.cwd,
            rollback=rollback,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
        )
        return self.stage.finish_execution_error(
            cwd=self.cwd,
            execution=execution,
            before_eval=preflight.before_eval,
            before_plan_path=preflight.before_plan_path,
            before_eval_path=preflight.before_eval_path,
            error=exc,
            citation_candidate_applied=dispatch_result.citation_candidate_applied,
        )


__all__ = ["QaLoopStepRunner"]
