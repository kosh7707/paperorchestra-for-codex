from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.citation_integrity_paths import (
    citation_integrity_audit_path,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
)
from paperorchestra.reviews.citation_rendered_references import rendered_reference_audit_path


def _payload_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("status") or payload.get("verdict") or payload.get("overall_status")
    return str(raw).strip().lower() if raw is not None else None


def _artifact_check(
    path: Path,
    *,
    expected_manuscript_sha256: str | None,
    missing_code: str,
    stale_code: str,
    failed_code: str,
    unbound_code: str | None = None,
    require_binding: bool = False,
) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "path": str(path),
            "sha256": None,
            "failing_codes": [missing_code],
            "reason": "missing_or_unreadable",
        }
    failing: list[str] = []
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(unbound_code or stale_code)
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(stale_code)
    status = _payload_status(payload)
    if status in {"fail", "failed", "reject", "rejected", "block", "blocked"}:
        failing.append(failed_code)
    for code in payload.get("failing_codes") or []:
        if isinstance(code, str) and code:
            failing.append(code)
    return {
        "status": "fail" if failing else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def _critic_review_artifact(
    name: str,
    path: Path,
    *,
    expected_manuscript_sha256: str | None,
    require_binding: bool,
) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "name": name,
            "path": str(path),
            "sha256": None,
            "artifact_status": None,
            "manuscript_sha256": None,
            "status": "fail",
            "failing_codes": [f"{name}_missing"],
            "reason": "missing_or_unreadable",
        }

    failing: list[str] = []
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(f"{name}_unbound")
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(f"{name}_stale")

    artifact_status = _payload_status(payload)
    if artifact_status not in {"pass", "ok", "warn", "warning"}:
        failing.append(f"{name}_{artifact_status or 'unknown'}")
    for code in payload.get("failing_codes") or []:
        if isinstance(code, str) and code:
            failing.append(code)

    return {
        "name": name,
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": artifact_status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "status": "fail" if failing else "pass",
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def build_citation_integrity_critic(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Build a deterministic critic packet over the citation integrity evidence.

    The artifact is intentionally non-generative: it does not approve citations
    by itself or invent missing reviewer judgment. It records that the
    claim-safe citation evidence surface exists, is bound to the current
    manuscript, and has already passed its concrete checks.
    """

    from paperorchestra.core.session import load_session

    state = load_session(cwd)
    manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    require_binding = quality_mode == "claim_safe"
    reviewed = [
        _critic_review_artifact(
            "rendered_reference_audit",
            rendered_reference_audit_path(cwd),
            expected_manuscript_sha256=manuscript_sha,
            require_binding=require_binding,
        ),
        _critic_review_artifact(
            "citation_intent_plan",
            citation_intent_plan_path(cwd),
            expected_manuscript_sha256=manuscript_sha,
            require_binding=require_binding,
        ),
        _critic_review_artifact(
            "citation_source_match",
            citation_source_match_path(cwd),
            expected_manuscript_sha256=manuscript_sha,
            require_binding=require_binding,
        ),
        _critic_review_artifact(
            "citation_integrity_audit",
            citation_integrity_audit_path(cwd),
            expected_manuscript_sha256=manuscript_sha,
            require_binding=require_binding,
        ),
    ]
    failing: list[str] = []
    for item in reviewed:
        failing.extend(str(code) for code in item.get("failing_codes") or [] if str(code))
    return {
        "schema_version": "citation-integrity-critic/1",
        "status": "fail" if failing else "pass",
        "quality_mode": quality_mode,
        "reviewer": "deterministic-citation-integrity-critic",
        "review_scope": [
            "rendered_reference_metadata_and_denominator",
            "citation_intent_and_placement_surface",
            "citation_source_match_support_status",
            "citation_density_duplicate_and_context_policy",
        ],
        "manuscript_sha256": manuscript_sha,
        "paper_full_tex_sha256": manuscript_sha,
        "reviewed_artifacts": reviewed,
        "failing_codes": sorted(dict.fromkeys(failing)),
        "verdict_rationale": "all reviewed citation evidence artifacts passed"
        if not failing
        else "one or more reviewed citation evidence artifacts failed, were skipped, missing, stale, or unbound",
    }


def write_citation_integrity_critic(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload = build_citation_integrity_critic(cwd, quality_mode=quality_mode)
    path = citation_integrity_critic_path(cwd)
    write_json(path, payload)
    if output_path:
        extra_path = Path(output_path).resolve()
        if extra_path != path:
            write_json(extra_path, payload)
            return extra_path, payload
    return path, payload


def citation_integrity_check(cwd: str | Path | None, state: Any, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Return the claim-safe Citation Integrity/Critic gate status."""

    expected_manuscript_sha256 = _file_sha256(state.artifacts.paper_full_tex)
    integrity = _artifact_check(
        citation_integrity_audit_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_integrity_missing",
        stale_code="citation_integrity_stale",
        failed_code="citation_integrity_failed",
        unbound_code="citation_integrity_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    critic = _artifact_check(
        citation_integrity_critic_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_critic_missing",
        stale_code="citation_critic_stale",
        failed_code="citation_critic_failed",
        unbound_code="citation_critic_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    rendered = _artifact_check(
        rendered_reference_audit_path(cwd),
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="rendered_reference_audit_missing",
        stale_code="rendered_reference_audit_stale",
        failed_code="rendered_reference_audit_failed",
        unbound_code="rendered_reference_audit_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    failing_codes: list[str] = []
    if quality_mode == "claim_safe":
        failing_codes.extend(integrity["failing_codes"])
        failing_codes.extend(critic["failing_codes"])
        failing_codes.extend(rendered["failing_codes"])
    else:
        for check in (integrity, critic, rendered):
            failing_codes.extend(code for code in check["failing_codes"] if not code.endswith("_missing"))
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "manuscript_sha256": expected_manuscript_sha256,
        "citation_integrity_audit": integrity,
        "citation_integrity_critic": critic,
        "rendered_reference_audit": rendered,
        "mode_effect": (
            "hard_fail_in_claim_safe"
            if quality_mode == "claim_safe"
            else "missing_artifacts_allowed_outside_claim_safe"
        ),
    }
