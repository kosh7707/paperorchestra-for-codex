from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path
from paperorchestra.feedback import packet_bindings as _packet_bindings


def _validate_current_operator_plan(
    *,
    cwd: str | Path | None,
    session_id: str,
    current_manuscript_sha256: str,
    allow_operator_review_context: bool = False,
) -> None:
    plan_path = artifact_path(cwd, "qa-loop.plan.json")
    try:
        plan = read_json(plan_path)
    except Exception as exc:
        raise ContractError("operator feedback requires readable current qa-loop.plan.json") from exc
    if not isinstance(plan, dict):
        raise ContractError("operator feedback requires readable current qa-loop.plan.json")
    plan_verdict = plan.get("verdict")
    if allow_operator_review_context:
        if plan_verdict not in {"continue", "human_needed"}:
            raise ContractError(
                "operator feedback operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"
            )
    elif plan_verdict != "human_needed":
        raise ContractError("operator feedback requires current qa-loop.plan.json verdict=human_needed")
    if plan.get("session_id") != session_id:
        raise ContractError("operator feedback current qa-loop.plan.json session_id mismatch")
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha("qa_loop_plan", plan)
    if bound_sha is None:
        raise ContractError("operator feedback current qa-loop.plan.json lacks manuscript hash binding")
    if bound_sha != current_manuscript_sha256:
        raise ContractError("operator feedback current qa-loop.plan.json is stale for current manuscript")
