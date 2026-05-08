from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import write_json
from .models import utc_now_iso
from .pipeline import refine_current_paper
from .quality_loop import write_quality_eval, write_quality_loop_plan
from .quality_loop_history import _failing_codes_from_quality_eval
from .session import artifact_path, load_session, save_session

QUALITY_GATE_SCHEMA_VERSION = "quality-gate/1"
QUALITY_GATE_PROFILES = {"auto", "mock", "ralph", "claim_safe"}


def _normalize_profile(profile: str | None, quality_eval: dict[str, Any]) -> str:
    requested = (profile or "auto").strip().lower().replace("-", "_")
    if requested not in QUALITY_GATE_PROFILES:
        raise ValueError(f"Unknown quality-gate profile {profile!r}; expected one of: {', '.join(sorted(QUALITY_GATE_PROFILES))}")
    if requested != "auto":
        return requested
    mode = str(quality_eval.get("mode") or "").strip().lower()
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    if provenance.get("level") == "mock":
        return "mock"
    if mode == "claim_safe":
        return "claim_safe"
    return "ralph"


def _tier_status(quality_eval: dict[str, Any], tier_name: str) -> str:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers.get(tier_name), dict) else {}
    return str(tier.get("status") or "missing")


def _tier_codes(quality_eval: dict[str, Any], tier_name: str) -> list[str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers.get(tier_name), dict) else {}
    return [str(code) for code in (tier.get("failing_codes") or []) if code]


def _dimension(
    *,
    name: str,
    status: str,
    blocking: bool,
    failing_codes: list[str] | None = None,
    sources: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "blocking": bool(blocking),
        "failing_codes": sorted(dict.fromkeys(failing_codes or [])),
        "sources": sources or [],
        "details": details or {},
    }


def _status_for_profile(raw_status: str, *, profile: str, axis: str) -> tuple[str, bool]:
    if raw_status in {"pass", "never_automated"}:
        return ("pass" if raw_status == "pass" else "human_owned", False)
    if raw_status.startswith("skipped"):
        return ("block" if profile == "claim_safe" else "warn", profile == "claim_safe")
    if raw_status == "fail":
        if profile == "mock" and axis in {"story_logic", "citation_claim_safety", "reviewer_acceptability", "reproducibility"}:
            return "warn", False
        return "block", True
    if raw_status == "warn":
        return ("block", True) if profile == "claim_safe" else ("warn", False)
    return ("warn", False) if profile == "mock" else ("block", True)


def _repair_action_ids(plan: dict[str, Any], codes: set[str]) -> list[str]:
    action_ids: list[str] = []
    for action in plan.get("repair_actions") or []:
        if not isinstance(action, dict):
            continue
        if str(action.get("code") or "") in codes:
            action_id = str(action.get("id") or "")
            if action_id:
                action_ids.append(action_id)
    return sorted(dict.fromkeys(action_ids))


def build_quality_gate_report(
    quality_eval: dict[str, Any],
    plan: dict[str, Any],
    *,
    profile: str = "auto",
    quality_eval_path: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_profile = _normalize_profile(profile, quality_eval)
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    non_reviewable = quality_eval.get("non_reviewable") if isinstance(quality_eval.get("non_reviewable"), dict) else {}
    dimensions: dict[str, dict[str, Any]] = {}

    tier0_status = _tier_status(quality_eval, "tier_0_preconditions")
    tier1_status = _tier_status(quality_eval, "tier_1_structural")
    structural_codes = _tier_codes(quality_eval, "tier_0_preconditions") + _tier_codes(quality_eval, "tier_1_structural")
    structural_codes += [str(code) for code in (non_reviewable.get("failing_codes") or []) if code]
    structural_raw = "fail" if structural_codes or tier0_status == "fail" or tier1_status == "fail" else "pass"
    structural_status, structural_blocking = _status_for_profile(structural_raw, profile=resolved_profile, axis="structure_latex")
    dimensions["structure_latex"] = _dimension(
        name="LaTeX, structure, artifact freshness",
        status=structural_status,
        blocking=structural_blocking,
        failing_codes=structural_codes,
        sources=["tier_0_preconditions", "tier_1_structural", "non_reviewable"],
        details={
            "tier_0_status": tier0_status,
            "tier_1_status": tier1_status,
            "non_reviewable_status": non_reviewable.get("status"),
            "repair_action_ids": _repair_action_ids(plan, set(structural_codes)),
        },
    )

    tier2_status = _tier_status(quality_eval, "tier_2_claim_safety")
    claim_codes = _tier_codes(quality_eval, "tier_2_claim_safety")
    claim_status, claim_blocking = _status_for_profile(tier2_status, profile=resolved_profile, axis="citation_claim_safety")
    dimensions["citation_claim_safety"] = _dimension(
        name="Citation fidelity and claim safety",
        status=claim_status,
        blocking=claim_blocking,
        failing_codes=claim_codes,
        sources=["tier_2_claim_safety"],
        details={"repair_action_ids": _repair_action_ids(plan, set(claim_codes))},
    )

    story_codes = [
        code
        for code in claim_codes
        if code
        in {
            "planning_satisfaction_missing",
            "planning_satisfaction_stale",
            "planning_satisfaction_failed",
            "narrative_plan_missing",
            "claim_map_missing",
            "citation_placement_plan_missing",
            "expected_section_missing",
            "expected_section_too_shallow",
        }
    ]
    story_raw = "fail" if story_codes else ("warn" if tier2_status.startswith("skipped") else "pass")
    story_status, story_blocking = _status_for_profile(story_raw, profile=resolved_profile, axis="story_logic")
    dimensions["story_logic"] = _dimension(
        name="Narrative logic, positioning, and section story",
        status=story_status,
        blocking=story_blocking,
        failing_codes=story_codes,
        sources=["planning_artifacts", "tier_2_claim_safety"],
        details={"repair_action_ids": _repair_action_ids(plan, set(story_codes))},
    )

    tier3_status = _tier_status(quality_eval, "tier_3_scholarly_quality")
    tier3_codes = _tier_codes(quality_eval, "tier_3_scholarly_quality")
    reviewer_status, reviewer_blocking = _status_for_profile(tier3_status, profile=resolved_profile, axis="reviewer_acceptability")
    tier3 = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    dimensions["reviewer_acceptability"] = _dimension(
        name="Reviewer acceptability and scholarly quality",
        status=reviewer_status,
        blocking=reviewer_blocking,
        failing_codes=tier3_codes,
        sources=["tier_3_scholarly_quality", "review.latest.json", "section_review"],
        details={
            "overall_score": tier3.get("overall_score"),
            "axis_scores": tier3.get("axis_scores"),
            "anti_inflation_triggered": bool(tier3.get("anti_inflation_triggered")),
            "repair_action_ids": _repair_action_ids(plan, set(tier3_codes)),
        },
    )

    repro_snapshot = plan.get("audit_snapshots", {}).get("reproducibility") if isinstance(plan.get("audit_snapshots"), dict) else {}
    fidelity_snapshot = plan.get("audit_snapshots", {}).get("fidelity") if isinstance(plan.get("audit_snapshots"), dict) else {}
    repro_codes: list[str] = []
    provenance_level = str(provenance.get("level") or "unknown")
    if resolved_profile == "claim_safe" and provenance_level != "live":
        repro_codes.append(f"provenance_not_live:{provenance_level}")
    if isinstance(repro_snapshot, dict) and repro_snapshot.get("verdict") == "BLOCK":
        repro_codes.append("reproducibility_block")
    if isinstance(fidelity_snapshot, dict) and str(fidelity_snapshot.get("overall_status") or "") == "fail":
        repro_codes.append("fidelity_fail")
    repro_raw = "fail" if repro_codes else ("warn" if provenance_level in {"mock", "mixed", "unknown"} else "pass")
    repro_status, repro_blocking = _status_for_profile(repro_raw, profile=resolved_profile, axis="reproducibility")
    dimensions["reproducibility"] = _dimension(
        name="Experiment, method, provenance, and reproducibility evidence",
        status=repro_status,
        blocking=repro_blocking,
        failing_codes=repro_codes,
        sources=["reproducibility_audit", "fidelity_audit", "provenance_trust"],
        details={
            "provenance_level": provenance_level,
            "reproducibility_verdict": repro_snapshot.get("verdict") if isinstance(repro_snapshot, dict) else None,
            "fidelity_status": fidelity_snapshot.get("overall_status") if isinstance(fidelity_snapshot, dict) else None,
        },
    )

    tier4 = tiers.get("tier_4_human_finalization") if isinstance(tiers.get("tier_4_human_finalization"), dict) else {}
    dimensions["human_finalization"] = _dimension(
        name="Human-owned final proof, bibliography curation, venue fit, and submission decision",
        status="human_owned",
        blocking=False,
        failing_codes=[],
        sources=["tier_4_human_finalization"],
        details={"outstanding_owners": tier4.get("outstanding_owners", [])},
    )

    blocked_dimensions = [key for key, value in dimensions.items() if value.get("blocking")]
    warn_dimensions = [key for key, value in dimensions.items() if value.get("status") == "warn"]
    if blocked_dimensions:
        verdict = "block"
    elif warn_dimensions or plan.get("repair_actions"):
        verdict = "repairable"
    else:
        verdict = "pass"
    return {
        "schema_version": QUALITY_GATE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": quality_eval.get("session_id") or plan.get("session_id"),
        "profile": resolved_profile,
        "requested_profile": profile,
        "quality_mode": quality_eval.get("mode"),
        "strict_gate": True,
        "mock_policy": "loose: structural/non-reviewable issues still block; claim, provenance, and reviewer issues warn unless promoted by profile",
        "claim_safe_policy": "strict: any failed/skipped/warned Tier 0-3 dimension blocks until repaired or explicitly accepted where supported",
        "decision": {
            "verdict": verdict,
            "blocked": bool(blocked_dimensions),
            "blocked_dimensions": blocked_dimensions,
            "warning_dimensions": warn_dimensions,
            "plan_verdict": plan.get("verdict"),
            "plan_verdict_rationale": plan.get("verdict_rationale"),
        },
        "dimensions": dimensions,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "repair_actions": plan.get("repair_actions", []),
        "next_commands": _next_commands(verdict, resolved_profile),
        "source_artifacts": {
            "quality_eval": str(quality_eval_path) if quality_eval_path else None,
            "qa_loop_plan": str(plan_path) if plan_path else None,
            **(plan.get("source_artifacts") if isinstance(plan.get("source_artifacts"), dict) else {}),
        },
        "quality_eval_summary": plan.get("quality_eval_summary"),
    }


def _next_commands(verdict: str, profile: str) -> list[str]:
    commands = [
        "paperorchestra quality-eval --quality-mode claim_safe" if profile == "claim_safe" else "paperorchestra quality-eval --quality-mode draft",
        "paperorchestra qa-loop-plan --quality-mode claim_safe" if profile == "claim_safe" else "paperorchestra qa-loop-plan --quality-mode draft",
    ]
    if verdict in {"block", "repairable"}:
        commands.append("paperorchestra quality-gate --auto-refine --refine-iterations 1")
    commands.append("paperorchestra status --summary")
    return commands


def write_quality_gate(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    plan_output_path: str | Path | None = None,
    profile: str = "auto",
    quality_mode: str = "draft",
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    max_iterations: int = 10,
    auto_refine: bool = False,
    provider: Any | None = None,
    refine_iterations: int = 1,
    runtime_mode: str = "compatibility",
    require_compile_for_accept: bool = False,
) -> tuple[Path, dict[str, Any]]:
    quality_eval_path, quality_eval = write_quality_eval(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
    )
    plan_path, plan = write_quality_loop_plan(
        cwd,
        plan_output_path,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=quality_eval_path,
    )
    report = build_quality_gate_report(
        quality_eval,
        plan,
        profile=profile,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
    )
    auto_improvement: dict[str, Any] = {
        "attempted": False,
        "reason": "not requested",
    }
    if auto_refine:
        if provider is None:
            auto_improvement = {"attempted": False, "reason": "provider is required for --auto-refine"}
        elif report["decision"]["verdict"] == "pass":
            auto_improvement = {"attempted": False, "reason": "quality gate already passed"}
        else:
            before = report["decision"]
            refine_result = refine_current_paper(
                cwd,
                provider,
                iterations=max(1, int(refine_iterations)),
                require_compile_for_accept=require_compile_for_accept,
                runtime_mode=runtime_mode,
            )
            quality_eval_path, quality_eval = write_quality_eval(
                cwd,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
            )
            plan_path, plan = write_quality_loop_plan(
                cwd,
                plan_output_path,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                accept_mixed_provenance=accept_mixed_provenance,
                quality_eval_input_path=quality_eval_path,
            )
            report = build_quality_gate_report(
                quality_eval,
                plan,
                profile=profile,
                quality_eval_path=quality_eval_path,
                plan_path=plan_path,
            )
            auto_improvement = {
                "attempted": True,
                "before_decision": before,
                "after_decision": report["decision"],
                "refine_result": refine_result,
            }
    report["auto_improvement"] = auto_improvement
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "quality-gate.report.json")
    write_json(path, report)
    state = load_session(cwd)
    state.notes.append(f"Quality gate recorded: {path.name}")
    save_session(cwd, state)
    return path, report
