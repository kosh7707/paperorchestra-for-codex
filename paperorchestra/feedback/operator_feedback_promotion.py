from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.feedback.operator_candidates import _promote_candidate_text
from paperorchestra.feedback.operator_feedback_options import OperatorFeedbackOptions
from paperorchestra.feedback.operator_verification import _verification_block, _verification_snapshot
from paperorchestra.runtime.providers import BaseProvider


@dataclass(frozen=True)
class OperatorFeedbackPromotion:
    verification: dict[str, Any]


def promote_operator_feedback_attempt(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    snapshot: dict[str, Any],
    execution: dict[str, Any],
    candidate_result: dict[str, Any],
    attempt_record: dict[str, Any],
    attempt_index: int,
    options: OperatorFeedbackOptions,
) -> OperatorFeedbackPromotion:
    execution["promotion_status"] = "promoted"
    execution["promotion_reason"] = "operator_candidate_passed_hard_gate"
    _promote_candidate_text(cwd, candidate_result["candidate_path"], snapshot.get("paper_path"))
    verification = _verification_snapshot(
        cwd,
        provider=provider,
        **options.verification_kwargs(f"validation.operator-feedback.promoted-{attempt_index:02d}.json"),
    )
    execution["post_promotion_qa_verdict"] = str(verification["plan"].get("verdict"))
    attempt_record["promoted_canonical_verification"] = _verification_block(verification)
    return OperatorFeedbackPromotion(verification=verification)
