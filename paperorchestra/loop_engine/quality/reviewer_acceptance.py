from __future__ import annotations

from pathlib import Path
from typing import Any

from . import review_score as _review_score
from .utils import _file_sha256, _read_json_if_exists
from paperorchestra.core.session import runtime_root


def _reviewer_acceptance_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / "reviewer-independence-acceptance.json"


def _reviewer_independence_acceptance(
    cwd: str | Path | None,
    current_sha: str | None,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    path = _reviewer_acceptance_path(cwd)
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {"status": "missing", "path": str(path), "failing_codes": ["reviewer_independence_missing"]}

    failures: list[str] = []
    if payload.get("schema_version") != "reviewer-independence-acceptance/1":
        failures.append("reviewer_independence_acceptance_legacy_untrusted")
    if payload.get("source") == "codex_operator" or payload.get("not_independent_human_review") is True:
        failures.append("reviewer_independence_acceptance_operator_not_independent")
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        failures.append("reviewer_independence_acceptance_stale")

    accepted_hashes = {
        str(item.get("sha256"))
        for item in payload.get("review_artifacts") or []
        if isinstance(item, dict) and item.get("sha256")
    }
    current_hashes = {str(record.get("sha256")) for record in records if record.get("sha256")}
    if not current_hashes or not current_hashes.issubset(accepted_hashes):
        failures.append("reviewer_independence_acceptance_stale")

    if (
        not _review_score._nonempty_string(payload.get("rationale"), min_len=10)
        or not _review_score._nonempty_string(payload.get("operator_label"), min_len=2)
    ):
        failures.append("reviewer_independence_acceptance_incomplete")
    if not _review_score._nonempty_string(payload.get("accepted_at"), min_len=10):
        failures.append("reviewer_independence_acceptance_incomplete")

    writer_refiner = payload.get("writer_refiner_provenance")
    if not isinstance(writer_refiner, list) or not writer_refiner:
        failures.append("reviewer_independence_acceptance_incomplete")
    else:
        for item in writer_refiner:
            if not isinstance(item, dict):
                failures.append("reviewer_independence_acceptance_incomplete")
                continue
            path_value = item.get("path")
            expected_sha = item.get("sha256")
            actual_sha = _file_sha256(path_value) if isinstance(path_value, str) else None
            if not path_value or not expected_sha or not actual_sha or expected_sha != actual_sha:
                failures.append("reviewer_independence_acceptance_stale")

    return {
        "status": "fail" if failures else "pass",
        "path": str(path),
        "failing_codes": sorted(dict.fromkeys(failures)),
        "review_artifact_count": len(payload.get("review_artifacts") or []),
    }
