from __future__ import annotations

from paperorchestra.orchestra.executor import ActionExecutor, ExecutionRecord
from paperorchestra.orchestra.state import NextAction, OrchestraState


def execute_action_protected(
    executor: ActionExecutor,
    action: NextAction,
    state: OrchestraState,
) -> ExecutionRecord:
    protected_snapshot = state.to_dict(include_private=True)
    record = executor.execute(action, state)
    if state.to_dict(include_private=True) != protected_snapshot:
        raise ValueError("ActionExecutor must not mutate OrchestraState during bounded execution.")
    return record


def append_execution_evidence(state: OrchestraState, record: ExecutionRecord) -> None:
    if not record.evidence_refs:
        return
    state.evidence_refs.append(
        {
            "kind": "orchestrator_execution_record",
            "payload": record.to_public_dict(),
        }
    )
