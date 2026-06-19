from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.reviews.citation_integrity_paths import (
    citation_integrity_audit_path,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
)
from paperorchestra.reviews.citation_rendered_references import rendered_reference_audit_path
from paperorchestra.reviews.citation_artifact_checks import (
    _artifact_check,
    _critic_review_artifact,
    _payload_status,
)


_CRITIC_ARTIFACTS = (
    ("rendered_reference_audit", rendered_reference_audit_path),
    ("citation_intent_plan", citation_intent_plan_path),
    ("citation_source_match", citation_source_match_path),
    ("citation_integrity_audit", citation_integrity_audit_path),
)

_GATE_ARTIFACTS = (
    ("citation_integrity_audit", citation_integrity_audit_path, "citation_integrity"),
    ("citation_integrity_critic", citation_integrity_critic_path, "citation_critic"),
    ("rendered_reference_audit", rendered_reference_audit_path, "rendered_reference_audit"),
)


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
            name,
            path_fn(cwd),
            expected_manuscript_sha256=manuscript_sha,
            require_binding=require_binding,
        )
        for name, path_fn in _CRITIC_ARTIFACTS
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
    require_binding = quality_mode == "claim_safe"
    checks = {
        key: _artifact_check(
            path_fn(cwd),
            expected_manuscript_sha256=expected_manuscript_sha256,
            missing_code=f"{prefix}_missing",
            stale_code=f"{prefix}_stale",
            failed_code=f"{prefix}_failed",
            unbound_code=f"{prefix}_unbound",
            require_binding=require_binding,
        )
        for key, path_fn, prefix in _GATE_ARTIFACTS
    }
    failing_codes: list[str] = []
    for check in checks.values():
        failing_codes.extend(
            check["failing_codes"]
            if require_binding
            else [code for code in check["failing_codes"] if not code.endswith("_missing")]
        )
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "manuscript_sha256": expected_manuscript_sha256,
        "citation_integrity_audit": checks["citation_integrity_audit"],
        "citation_integrity_critic": checks["citation_integrity_critic"],
        "rendered_reference_audit": checks["rendered_reference_audit"],
        "mode_effect": (
            "hard_fail_in_claim_safe"
            if quality_mode == "claim_safe"
            else "missing_artifacts_allowed_outside_claim_safe"
        ),
    }
