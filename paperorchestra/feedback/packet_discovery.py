from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.packet_bound_paths import _current_bound_execution_path
from paperorchestra.feedback.packet_execution_discovery import (
    _latest_human_needed_execution,
    _latest_human_needed_operator_feedback_execution,
)
from paperorchestra.feedback.packet_execution_openers import _execution_payload_opens_operator_review


def _operator_review_human_needed_artifacts(cwd: str | Path | None) -> tuple[Path | None, Path | None, Path | None]:
    plan_path = artifact_path(cwd, "qa-loop.plan.json")
    qa_plan_path = plan_path if plan_path.exists() and plan_path.is_file() else None
    qa_execution_path = _latest_human_needed_execution(cwd)
    operator_execution_path = _latest_human_needed_operator_feedback_execution(cwd)
    state = load_session(cwd)
    current_sha = _packet_bindings._normalized_sha(_packet_artifacts._file_sha256(state.artifacts.paper_full_tex))
    if qa_plan_path is not None:
        plan = read_json(qa_plan_path)
        if isinstance(plan, dict) and plan.get("verdict") == "human_needed":
            return (
                qa_plan_path,
                _current_bound_execution_path(
                    qa_execution_path,
                    role="qa_loop_execution",
                    current_manuscript_sha256=current_sha,
                ),
                _current_bound_execution_path(
                    operator_execution_path,
                    role="operator_feedback_execution",
                    current_manuscript_sha256=current_sha,
                ),
            )
    if qa_plan_path is not None and qa_execution_path is not None and current_sha:
        try:
            execution = read_json(qa_execution_path)
        except Exception:
            execution = None
        if isinstance(execution, dict) and _execution_payload_opens_operator_review(
            qa_execution_path,
            execution,
            current_manuscript_sha256=current_sha,
        ):
            return (
                qa_plan_path,
                qa_execution_path,
                _current_bound_execution_path(
                    operator_execution_path,
                    role="operator_feedback_execution",
                    current_manuscript_sha256=current_sha,
                ),
            )
    raise ContractError(
        "operator feedback requires current qa-loop.plan.json verdict=human_needed "
        "or a hash-bound latest qa-loop execution that opens an operator review stop; "
        "stale QA/operator-feedback execution artifacts cannot reopen the operator lane"
    )
