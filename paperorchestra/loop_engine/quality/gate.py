from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.loop_engine.quality.gate_dimensions import (
    QUALITY_GATE_PROFILES,
    build_quality_gate_dimension_bundle,
    dimension as _dimension,
    normalize_profile as _normalize_profile,
    repair_action_ids as _repair_action_ids,
    status_for_profile as _status_for_profile,
    tier_codes as _tier_codes,
    tier_status as _tier_status,
)
from paperorchestra.loop_engine.quality.history import _failing_codes_from_quality_eval
from paperorchestra.loop_engine.quality.loop import write_quality_eval, write_quality_loop_plan

QUALITY_GATE_SCHEMA_VERSION = "quality-gate/1"

# Compatibility aliases for legacy tests/extensions that imported private
# helpers from this module before dimension logic was split out.
__all__ = [
    "QUALITY_GATE_PROFILES",
    "QUALITY_GATE_SCHEMA_VERSION",
    "_dimension",
    "_normalize_profile",
    "_next_commands",
    "_repair_action_ids",
    "_status_for_profile",
    "_tier_codes",
    "_tier_status",
    "build_quality_gate_report",
    "write_quality_gate",
]


def build_quality_gate_report(
    quality_eval: dict[str, Any],
    plan: dict[str, Any],
    *,
    profile: str = "auto",
    quality_eval_path: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    bundle = build_quality_gate_dimension_bundle(quality_eval, plan, profile=profile)
    return {
        "schema_version": QUALITY_GATE_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": quality_eval.get("session_id") or plan.get("session_id"),
        "profile": bundle.resolved_profile,
        "requested_profile": profile,
        "quality_mode": quality_eval.get("mode"),
        "strict_gate": True,
        "mock_policy": "loose: structural/non-reviewable issues still block; claim, provenance, and reviewer issues warn unless promoted by profile",
        "claim_safe_policy": "strict: any failed/skipped/warned Tier 0-3 dimension blocks until repaired or explicitly accepted where supported",
        "decision": {
            "verdict": bundle.verdict,
            "blocked": bool(bundle.blocked_dimensions),
            "blocked_dimensions": bundle.blocked_dimensions,
            "warning_dimensions": bundle.warning_dimensions,
            "plan_verdict": plan.get("verdict"),
            "plan_verdict_rationale": plan.get("verdict_rationale"),
        },
        "dimensions": bundle.dimensions,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "repair_actions": plan.get("repair_actions", []),
        "next_commands": _next_commands(bundle.verdict, bundle.resolved_profile),
        "source_artifacts": {
            "quality_eval": str(quality_eval_path) if quality_eval_path else None,
            "qa_loop_plan": str(plan_path) if plan_path else None,
            **(plan.get("source_artifacts") if isinstance(plan.get("source_artifacts"), dict) else {}),
        },
        "quality_eval_summary": plan.get("quality_eval_summary"),
    }


def _next_commands(verdict: str, profile: str) -> list[str]:
    commands = [
        "paperorchestra qa-loop --quality-mode claim_safe" if profile == "claim_safe" else "paperorchestra qa-loop --quality-mode draft",
        "paperorchestra qa-loop --quality-mode claim_safe" if profile == "claim_safe" else "paperorchestra qa-loop --quality-mode draft",
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
