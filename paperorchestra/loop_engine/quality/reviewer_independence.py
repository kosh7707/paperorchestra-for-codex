from __future__ import annotations

from pathlib import Path
from typing import Any

from .reviewer_acceptance import _reviewer_acceptance_path, _reviewer_independence_acceptance
from .reviewer_records import _current_review_records, _reviewer_identity
from .utils import _file_sha256


def _reviewer_independence_check(cwd: str | Path | None, state, *, quality_mode: str) -> dict[str, Any]:
    if quality_mode != "claim_safe":
        return {"status": "not_required", "failing_codes": []}
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    records = _current_review_records(state, current_sha)
    identities = sorted({str(record.get("identity")) for record in records if record.get("identity")})
    acceptance = _reviewer_independence_acceptance(cwd, current_sha, records)
    if len(identities) >= 2:
        return {
            "status": "pass",
            "failing_codes": [],
            "current_review_count": len(records),
            "distinct_reviewer_count": len(identities),
            "reviewers": identities,
            "acceptance": acceptance,
        }
    if acceptance.get("status") == "pass":
        return {
            "status": "pass",
            "failing_codes": [],
            "current_review_count": len(records),
            "distinct_reviewer_count": len(identities),
            "reviewers": identities,
            "acceptance": acceptance,
            "operator_override_used": True,
        }
    codes = ["reviewer_independence_missing"]
    codes.extend(acceptance.get("failing_codes") or [])
    return {
        "status": "fail",
        "failing_codes": sorted(dict.fromkeys(codes)),
        "current_review_count": len(records),
        "distinct_reviewer_count": len(identities),
        "reviewers": identities,
        "acceptance": acceptance,
    }


__all__ = [
    "_current_review_records",
    "_reviewer_acceptance_path",
    "_reviewer_identity",
    "_reviewer_independence_acceptance",
    "_reviewer_independence_check",
]
