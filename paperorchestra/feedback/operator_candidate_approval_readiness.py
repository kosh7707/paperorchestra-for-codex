from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.core.errors import ContractError

_REQUIRED_APPROVAL_KEYS = (
    "candidate_path",
    "candidate_sha256",
    "base_manuscript_sha256",
    "source_execution_path",
    "source_execution_sha256",
    "created_at",
)


@dataclass(frozen=True)
class CandidateApprovalReadiness:
    execution: dict[str, Any]
    execution_role: str
    approval: dict[str, Any]
    progress: dict[str, Any]
    candidate_state: Any
    restored_current_state: Any

    @classmethod
    def from_execution(cls, execution: dict[str, Any], execution_role: str) -> "CandidateApprovalReadiness":
        approval = execution.get("candidate_approval")
        progress = execution.get("candidate_progress")
        if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
            raise ContractError("approve_existing_candidate requires human_needed_candidate_ready evidence")
        missing = [key for key in _REQUIRED_APPROVAL_KEYS if not str(approval.get(key) or "").strip()]
        if missing:
            raise ContractError("approve_existing_candidate missing candidate_approval." + ", candidate_approval.".join(missing))
        if not isinstance(progress, dict) or progress.get("forward_progress") is not True:
            raise ContractError("approve_existing_candidate requires candidate_progress.forward_progress=true")
        for key in ("before_failing_codes", "after_failing_codes"):
            if key not in progress:
                raise ContractError(f"approve_existing_candidate missing candidate_progress.{key}")
        return cls(
            execution=execution,
            execution_role=execution_role,
            approval=approval,
            progress=progress,
            candidate_state=execution.get("candidate_state"),
            restored_current_state=execution.get("restored_current_state"),
        )

    def require_blocker_progress(self) -> None:
        before_codes = {str(code) for code in self.progress.get("before_failing_codes") or []}
        after_codes = {str(code) for code in self.progress.get("after_failing_codes") or []}
        citation_delta = self.progress.get("citation_issue_delta")
        citation_improved = isinstance(citation_delta, int) and citation_delta < 0
        if before_codes and not (before_codes - after_codes) and not citation_improved:
            raise ContractError("approve_existing_candidate requires resolved active blockers or reduced citation issue count")

    def require_verification_evidence(self) -> None:
        candidate_verification = self.candidate_state.get("verification") if isinstance(self.candidate_state, dict) else None
        restored_verification = (
            self.restored_current_state.get("verification") if isinstance(self.restored_current_state, dict) else None
        )
        if not isinstance(candidate_verification, dict) and not isinstance(restored_verification, dict):
            raise ContractError("approve_existing_candidate requires candidate_state.verification or restored_current_state.verification")
