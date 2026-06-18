from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _file_sha256


def _review_provenance_failures(review: dict[str, Any], *, current_sha: str | None, quality_mode: str) -> tuple[list[str], dict[str, Any]]:
    if quality_mode != "claim_safe":
        return [], {"status": "not_required"}
    provenance = review.get("review_provenance")
    if not isinstance(provenance, dict):
        return ["review_provenance_missing"], {"status": "fail", "reason": "missing"}

    failures = _review_provenance_contract_failures(provenance, current_sha=current_sha)
    return sorted(dict.fromkeys(failures)), {
        "status": "fail" if failures else "pass",
        "reviewer_label": provenance.get("reviewer_label"),
        "provider_name": provenance.get("provider_name"),
        "provider_command_digest": provenance.get("provider_command_digest"),
        "prompt_trace_meta_path": provenance.get("prompt_trace_meta_path"),
        "provider_identity_path": provenance.get("provider_identity_path"),
        "lane_manifest_path": provenance.get("lane_manifest_path"),
        "failing_codes": sorted(dict.fromkeys(failures)),
    }


def _review_provenance_contract_failures(provenance: dict[str, Any], *, current_sha: str | None) -> list[str]:
    failures: list[str] = []
    if provenance.get("schema_version") != "review-provenance/1":
        failures.append("review_provenance_legacy_untrusted")
    if provenance.get("stage") != "review":
        failures.append("review_provenance_stage_mismatch")
    if current_sha and provenance.get("manuscript_sha256") != current_sha:
        failures.append("review_provenance_stale")
    failures.extend(_missing_provenance_path_failures(provenance))
    failures.extend(_stale_provenance_hash_failures(provenance))
    return failures


def _missing_provenance_path_failures(provenance: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, code in [
        ("prompt_trace_meta_path", "review_provenance_missing"),
        ("provider_identity_path", "review_provenance_missing"),
        ("lane_manifest_path", "review_provenance_missing"),
    ]:
        value = provenance.get(key)
        if not value or not Path(str(value)).exists():
            failures.append(code)
    return failures


def _stale_provenance_hash_failures(provenance: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path_key, sha_key in [
        ("prompt_trace_meta_path", "prompt_trace_meta_sha256"),
        ("provider_identity_path", "provider_identity_sha256"),
        ("lane_manifest_path", "lane_manifest_sha256"),
    ]:
        path = provenance.get(path_key)
        expected = provenance.get(sha_key)
        actual = _file_sha256(path) if isinstance(path, str) else None
        if expected and actual and expected != actual:
            failures.append("review_provenance_stale")
    return failures
