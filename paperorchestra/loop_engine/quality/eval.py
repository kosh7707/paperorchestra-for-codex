from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session

from paperorchestra.loop_engine.quality.citation_support import _citation_support_path
from paperorchestra.loop_engine.quality.eval_claim_safety import build_claim_safety_tier
from paperorchestra.loop_engine.quality.eval_leakage_surface import build_leakage_surface
from paperorchestra.loop_engine.quality.eval_payload import (
    build_human_finalization_tier,
    build_quality_eval_payload,
    build_quality_source_artifacts,
)
from paperorchestra.loop_engine.quality.eval_preconditions import PreconditionContext, build_precondition_tier
from paperorchestra.loop_engine.quality.eval_scholarly import build_scholarly_quality_tier
from paperorchestra.loop_engine.quality.eval_structural import build_structural_tier
from paperorchestra.loop_engine.quality.eval_tiers import (
    _skipped_tier,
)
from paperorchestra.loop_engine.quality.history import _build_cross_iteration, _failing_codes_from_quality_eval
from paperorchestra.loop_engine.quality.policy import DEFAULT_MAX_ITERATIONS, QUALITY_MODES
from paperorchestra.loop_engine.quality.provenance_trust import _provenance_trust
from paperorchestra.loop_engine.quality.ralph_evidence_check import _ralph_evidence_check
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.manuscript.narrative_artifacts import planning_artifact_status
from paperorchestra.reviews.fidelity import run_fidelity_audit
from paperorchestra.reviews.reproducibility import build_reproducibility_audit


def _normalize_quality_mode(mode: str | None) -> str:
    normalized = (mode or "ralph").strip().lower().replace("-", "_")
    if normalized not in QUALITY_MODES:
        raise ValueError(f"Unknown quality mode {mode!r}; expected one of: {', '.join(sorted(QUALITY_MODES))}")
    return normalized


def build_quality_eval(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    require_live_verification: bool = False,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    reproducibility: dict[str, Any] | None = None,
    fidelity: dict[str, Any] | None = None,
    current_attempt_consumes_budget: bool = False,
) -> dict[str, Any]:
    mode = _normalize_quality_mode(quality_mode)
    state = load_session(cwd)
    reproducibility = reproducibility if reproducibility is not None else build_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    fidelity = fidelity if fidelity is not None else run_fidelity_audit(cwd)
    manuscript_hash = _file_sha256(state.artifacts.paper_full_tex)
    citation_support_review_path = _citation_support_path(cwd, state)
    citation_support_review_sha256 = _file_sha256(citation_support_review_path)
    ralph_evidence = _ralph_evidence_check(cwd, quality_mode=mode)
    provenance = _provenance_trust(reproducibility)

    paper_exists = bool(state.artifacts.paper_full_tex and Path(state.artifacts.paper_full_tex).exists())
    planning_status = planning_artifact_status(cwd)
    tier0_result = build_precondition_tier(
        PreconditionContext(
            paper_full_tex=state.artifacts.paper_full_tex,
            paper_exists=paper_exists,
            manuscript_hash=manuscript_hash,
            reproducibility=reproducibility,
            planning_status=planning_status,
        )
    )
    tiers: dict[str, Any] = {"tier_0_preconditions": tier0_result.tier}
    leakage_surface = build_leakage_surface(state)

    if tier0_result.tier["status"] == "fail":
        tiers["tier_1_structural"] = _skipped_tier("tier_0_preconditions failed")
        tiers["tier_2_claim_safety"] = _skipped_tier("tier_0_preconditions failed")
        tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_0_preconditions failed")
    else:
        tier1 = build_structural_tier(
            state=state,
            mode=mode,
            manuscript_hash=manuscript_hash,
            reproducibility=reproducibility,
            leakage=leakage_surface.leakage,
            pdf_text_scan_unavailable=leakage_surface.pdf_text_scan_unavailable,
        )
        tiers["tier_1_structural"] = tier1
        if tier1["status"] == "fail":
            tiers["tier_2_claim_safety"] = _skipped_tier("tier_1_structural failed")
            tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_1_structural failed")
        else:
            tier2 = build_claim_safety_tier(
                cwd=cwd,
                state=state,
                mode=mode,
                reproducibility=reproducibility,
                planning_status=planning_status,
                ralph_evidence=ralph_evidence,
            )
            tiers["tier_2_claim_safety"] = tier2
            if tier2["status"] == "fail":
                tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_2_claim_safety failed in claim-safe mode")
            else:
                tiers["tier_3_scholarly_quality"] = build_scholarly_quality_tier(
                    cwd=cwd,
                    state=state,
                    mode=mode,
                )

    tiers["tier_4_human_finalization"] = build_human_finalization_tier()
    source_artifacts = build_quality_source_artifacts(
        cwd=cwd,
        state=state,
        citation_support_review_path=citation_support_review_path,
        citation_support_review_sha256=citation_support_review_sha256,
        ralph_evidence=ralph_evidence,
    )
    payload = build_quality_eval_payload(
        state=state,
        mode=mode,
        manuscript_hash=manuscript_hash,
        provenance=provenance,
        non_reviewable=leakage_surface.non_reviewable,
        tiers=tiers,
        source_artifacts=source_artifacts,
        reproducibility=reproducibility,
        fidelity=fidelity,
    )
    tier3_payload = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    current_axis_scores = (
        tier3_payload.get("axis_scores")
        if isinstance(tier3_payload, dict) and isinstance(tier3_payload.get("axis_scores"), dict)
        else {}
    )
    payload["cross_iteration"] = _build_cross_iteration(
        cwd,
        state.session_id,
        payload.get("manuscript_hash"),
        _failing_codes_from_quality_eval(payload),
        max_iterations,
        current_axis_scores=current_axis_scores,
        current_attempt_consumes_budget=current_attempt_consumes_budget,
    )
    return payload
