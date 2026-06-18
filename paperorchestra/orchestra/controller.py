from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.orchestra import FullLoopPlanner, LoopFacts
from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.controller_execution import append_execution_evidence, execute_action_protected
from paperorchestra.orchestra.controller_inspection import _inspect_state
from paperorchestra.orchestra.controller_result import OrchestratorRunResult
from paperorchestra.orchestra.controller_run_loop import _run_until_blocked
from paperorchestra.orchestra.controller_transitions import (
    _apply_local_execution_record,
    _execution_label,
)
from paperorchestra.orchestra.executor import ActionExecutor, ExecutionRecord
from paperorchestra.orchestra.omx_action_executor import OmxActionExecutor
from paperorchestra.orchestra.omx_runners import OmxCommandRunner
from paperorchestra.orchestra.planner import ActionPlanner
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.state import OrchestraState


class OrchestraOrchestrator:
    def __init__(self, cwd: str | Path | None = None) -> None:
        self.cwd = Path(cwd or ".").resolve()

    def inspect_state(self, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
        return _inspect_state(self.cwd, material_path=material_path, strict_omx=strict_omx)

    def run_until_blocked(self, *, material_path: str | Path | None = None) -> OrchestratorRunResult:
        return self._result_from_state(_run_until_blocked(self.cwd, material_path=material_path))

    def plan_full_loop(
        self,
        *,
        material_path: str | Path | None = None,
        state: OrchestraState | None = None,
        scoring_bundle: ScoringInputBundle | None = None,
        score: ScholarlyScore | None = None,
        consensus: CriticConsensus | None = None,
        high_risk_readiness: bool = False,
        compiled: bool = False,
        exported: bool = False,
    ) -> OrchestratorRunResult:
        current = state.clone() if state is not None else self.inspect_state(material_path=material_path)
        decision = FullLoopPlanner().plan(
            LoopFacts(
                state=current,
                scoring_bundle=scoring_bundle,
                score=score,
                consensus=consensus,
                high_risk_readiness=high_risk_readiness,
                compiled=compiled,
                exported=exported,
            )
        )
        planned_state = decision.state
        planned_state.next_actions = decision.actions
        return OrchestratorRunResult(
            state=planned_state,
            execution="bounded_full_loop_plan",
            action_taken="none",
            execution_record=None,
        )

    def execute_omx_once(
        self,
        *,
        material_path: str | Path | None = None,
        runner: OmxCommandRunner | None = None,
        executor: ActionExecutor | None = None,
        timeout_seconds: float = 30.0,
        slug: str | None = None,
    ) -> OrchestratorRunResult:
        state = _run_until_blocked(self.cwd, material_path=material_path)
        if not state.next_actions:
            action = None
            record = ExecutionRecord(
                action_type="none",
                reason="no_omx_action_available",
                status="unsupported",
                adapter="omx",
                evidence_refs=[],
                state_rebuild_required=False,
            )
        else:
            action = state.next_actions[0]
            executor = executor or OmxActionExecutor(
                cwd=self.cwd,
                runner=runner,
                timeout_seconds=timeout_seconds,
                slug=slug,
            )
            record = execute_action_protected(executor, action, state)
            append_execution_evidence(state, record)
        return OrchestratorRunResult(
            state=state,
            execution="bounded_omx_execution",
            action_taken=action.action_type if action is not None else "none",
            execution_record=record,
        )

    def step(
        self,
        *,
        material_path: str | Path | None = None,
        objective: str | None = None,
        execute: bool = False,
        executor: ActionExecutor | None = None,
    ) -> OrchestratorRunResult:
        state = self.inspect_state(material_path=material_path)
        state.next_actions = ActionPlanner().plan(state, objective=objective)
        if not execute:
            return self._result_from_state(state)
        if executor is None:
            raise ValueError("Explicit ActionExecutor is required when execute=True.")
        if not state.next_actions:
            return OrchestratorRunResult(
                state=state,
                execution="bounded_fake_execution",
                action_taken="none",
                execution_record=None,
            )
        action = state.next_actions[0]
        record = execute_action_protected(executor, action, state)
        append_execution_evidence(state, record)
        _apply_local_execution_record(state, record.to_public_dict())
        return OrchestratorRunResult(
            state=state,
            execution=_execution_label(record),
            action_taken=action.action_type,
            execution_record=record,
        )

    def _result_from_state(self, state: OrchestraState) -> OrchestratorRunResult:
        return OrchestratorRunResult(state=state)


def inspect_state(cwd: str | Path | None = None, *, material_path: str | Path | None = None, strict_omx: bool = False) -> OrchestraState:
    return OrchestraOrchestrator(cwd).inspect_state(material_path=material_path, strict_omx=strict_omx)


def run_until_blocked(cwd: str | Path | None = None, *, material_path: str | Path | None = None) -> OrchestraState:
    return OrchestraOrchestrator(cwd).run_until_blocked(material_path=material_path).state
