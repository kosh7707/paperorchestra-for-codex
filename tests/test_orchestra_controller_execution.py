from __future__ import annotations

from paperorchestra.orchestra.controller_execution import execute_action_protected
from paperorchestra.orchestra.executor import ExecutionRecord
from paperorchestra.orchestra.state import NextAction, OrchestraState


class _MutatingExecutor:
    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        state.blocking_reasons.append("mutated")
        return ExecutionRecord(action.action_type, action.reason, "executed_fake", "fake")


def test_execute_action_protected_rejects_state_mutating_executor(tmp_path) -> None:
    state = OrchestraState.new(cwd=tmp_path)
    action = NextAction("demo", "reason")

    try:
        execute_action_protected(_MutatingExecutor(), action, state)
    except ValueError as exc:
        assert "must not mutate OrchestraState" in str(exc)
    else:  # pragma: no cover - failure path is explicit for clearer assertion messages
        raise AssertionError("mutating executor should be rejected")
