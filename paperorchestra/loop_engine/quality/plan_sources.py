from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .utils import _file_sha256


@dataclass(frozen=True)
class CitationReviewIdentity:
    expected_sha256: Any
    current_sha256: str | None
    status: str


def build_quality_eval_for_plan(
    quality_eval: Mapping[str, Any], citation_support_review_path: str | Path
) -> tuple[dict[str, Any], CitationReviewIdentity]:
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}
    expected_sha256 = source_artifacts.get("citation_review_sha256")
    current_sha256 = _file_sha256(citation_support_review_path)
    identity = CitationReviewIdentity(
        expected_sha256=expected_sha256,
        current_sha256=current_sha256,
        status=_citation_review_identity_status(expected_sha256, current_sha256),
    )
    quality_eval_for_plan = dict(quality_eval)
    quality_eval_for_plan["source_artifacts"] = {
        **source_artifacts,
        "citation_review_current_sha256": identity.current_sha256,
        "citation_review_identity_status": identity.status,
    }
    return quality_eval_for_plan, identity


def _citation_review_identity_status(expected_sha256: Any, current_sha256: str | None) -> str:
    if expected_sha256 and current_sha256:
        return "pass" if expected_sha256 == current_sha256 else "stale_or_divergent"
    if expected_sha256 or current_sha256:
        return "missing_expected_or_current"
    return "missing"
