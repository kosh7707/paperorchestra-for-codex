from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.source_obligations import source_obligations_path
from paperorchestra.reviews.fidelity import run_fidelity_audit
from paperorchestra.reviews.reproducibility import build_reproducibility_audit, write_reproducibility_audit

from .actions import (
    _action,
    _citation_actions,
    _dedupe_actions,
    _fidelity_actions,
    _figure_review_actions,
    _generated_placeholder_figure_actions,
    _mode_actions,
    _strict_content_actions,
    _validation_actions,
    _warning_actions,
)
from .citation_support import _citation_support_path
from .eval import _mixed_provenance_acceptance, build_quality_eval
from .history import _failing_codes_from_quality_eval, _tier_statuses, quality_loop_history_path
from .plan_payload import QualityLoopPlanPayloadInput, build_quality_loop_plan_payload
from .plan_logic import (
    _plan_verdict,
    _quality_eval_actions,
)
from .plan_sources import build_quality_eval_for_plan
from .policy import (
    BUDGET_CONSUMING_HISTORY_EVENTS,
    CITATION_SUPPORT_REVIEW_REFRESH_CODES,
    DEFAULT_MAX_ITERATIONS,
    QA_LOOP_PLAN_SCHEMA_VERSION,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    REVIEW_REFRESH_CODES,
)
from .utils import _file_sha256, _sha256_jsonable


def build_quality_loop_plan(
    cwd: str | Path | None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    accept_mixed_provenance: bool = False,
    quality_eval: dict[str, Any] | None = None,
    quality_eval_path: str | Path | None = None,
) -> dict[str, Any]:
    state = load_session(cwd)
    reproducibility = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    fidelity = run_fidelity_audit(cwd)
    quality_eval = quality_eval or build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility,
        fidelity=fidelity,
    )
    citation_support_review_path = _citation_support_path(cwd, state)
    quality_eval_for_plan, citation_review_identity = build_quality_eval_for_plan(
        quality_eval,
        citation_support_review_path,
    )
    provenance_for_plan = dict(quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {})
    if provenance_for_plan.get("level") == "mixed" and accept_mixed_provenance:
        provenance_for_plan["mixed_acceptance"] = _mixed_provenance_acceptance(cwd, quality_eval)
    quality_eval_for_plan["provenance_trust"] = provenance_for_plan

    detailed_actions = (
        _citation_actions(reproducibility)
        + _validation_actions(reproducibility)
        + _figure_review_actions(state)
        + _generated_placeholder_figure_actions(state)
        + _mode_actions(reproducibility)
        + _warning_actions(reproducibility)
        + _fidelity_actions(fidelity)
        + _quality_eval_actions(quality_eval_for_plan)
    )
    if citation_review_identity.status != "pass":
        detailed_actions.append(
            _action(
                action_id="quality-eval:citation-support-identity",
                code="citation_support_review_stale",
                source=str(citation_support_review_path),
                target="claim safety",
                automation="automatic",
                reason="Citation-support review identity is missing, stale, or divergent from the quality-eval snapshot.",
                suggested_commands=["paperorchestra critique --citation-evidence-mode web", "paperorchestra qa-loop --quality-mode claim_safe"],
                ralph_instruction="Regenerate citation-support review and quality-eval before treating the QA loop plan as ready.",
            )
        )
    detailed_codes = {str(action.get("code")) for action in detailed_actions}
    strict_fallback_actions = [
        action for action in _strict_content_actions(reproducibility) if str(action.get("code")) not in detailed_codes
    ]
    actions = _dedupe_actions(detailed_actions + strict_fallback_actions)

    verdict, verdict_rationale = _plan_verdict(
        quality_eval_for_plan,
        actions,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    operator_packet_path = artifact_path(cwd, "operator_review_packet.json")
    operator_packet_sha = None
    if operator_packet_path.exists():
        try:
            packet_payload = read_json(operator_packet_path)
            if isinstance(packet_payload, dict):
                operator_packet_sha = packet_payload.get("packet_sha256")
        except Exception:
            operator_packet_sha = None
    return build_quality_loop_plan_payload(
        QualityLoopPlanPayloadInput(
            cwd=cwd,
            state=state,
            reproducibility=reproducibility,
            fidelity=fidelity,
            quality_eval=quality_eval,
            quality_eval_for_plan=quality_eval_for_plan,
            quality_eval_path=quality_eval_path,
            actions=actions,
            verdict=verdict,
            verdict_rationale=verdict_rationale,
            provenance_for_plan=provenance_for_plan,
            citation_support_review_path=citation_support_review_path,
            citation_review_identity=citation_review_identity,
            operator_packet_path=operator_packet_path,
            operator_packet_sha=operator_packet_sha,
            source_obligations_path=source_obligations_path(cwd),
        )
    )


def append_quality_loop_history(
    cwd: str | Path | None,
    quality_eval: dict[str, Any],
    *,
    verdict: str | None = None,
    plan_path: str | Path | None = None,
    quality_eval_path: str | Path | None = None,
    event_type: str = "quality_eval",
    consumes_budget: bool | None = None,
    execution_path: str | Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = quality_loop_history_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if consumes_budget is None:
        consumes_budget = event_type in BUDGET_CONSUMING_HISTORY_EVENTS
    entry = {
        "recorded_at": utc_now_iso(),
        "event_type": event_type,
        "consumes_budget": bool(consumes_budget),
        "session_id": quality_eval.get("session_id"),
        "mode": quality_eval.get("mode"),
        "manuscript_hash": quality_eval.get("manuscript_hash"),
        "quality_eval_path": str(quality_eval_path) if quality_eval_path else None,
        "plan_path": str(plan_path) if plan_path else None,
        "execution_path": str(execution_path) if execution_path else None,
        "quality_eval_sha256": f"sha256:{_file_sha256(quality_eval_path)}" if quality_eval_path else f"sha256:{_sha256_jsonable(quality_eval)}",
        "plan_sha256": f"sha256:{_file_sha256(plan_path)}" if plan_path else None,
        "verdict": verdict,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "tier_statuses": _tier_statuses(quality_eval),
        "tier_3_overall_score": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("overall_score") if isinstance(quality_eval.get("tiers"), dict) else None,
        "tier_3_axis_scores": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("axis_scores") if isinstance(quality_eval.get("tiers"), dict) else {},
    }
    if extra:
        entry.update(extra)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def write_quality_eval(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    append_history: bool = False,
    current_attempt_consumes_budget: bool = False,
) -> tuple[Path, dict[str, Any]]:
    fidelity_payload = run_fidelity_audit(cwd)
    fidelity_path = artifact_path(cwd, "fidelity.audit.json")
    write_json(fidelity_path, fidelity_payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(fidelity_path)
    save_session(cwd, state)
    write_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    reproducibility_payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    payload = build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility_payload,
        fidelity=fidelity_payload,
        current_attempt_consumes_budget=current_attempt_consumes_budget,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "quality-eval.json")
    write_json(path, payload)
    state = load_session(cwd)
    state.notes.append(f"Quality eval recorded: {path.name}")
    save_session(cwd, state)
    if append_history:
        append_quality_loop_history(cwd, payload, quality_eval_path=path, event_type="quality_eval", consumes_budget=False)
    return path, payload


def _validate_quality_eval_input(
    quality_eval: dict[str, Any],
    *,
    state,
    reproducibility: dict[str, Any],
    fidelity: dict[str, Any],
    quality_eval_path: Path,
) -> None:
    current_hash = _file_sha256(state.artifacts.paper_full_tex)
    expected_manuscript_hash = f"sha256:{current_hash}" if current_hash else None
    if quality_eval.get("manuscript_hash") != expected_manuscript_hash:
        raise ValueError(
            "quality-eval input is stale for the current manuscript: "
            f"{quality_eval_path} has {quality_eval.get('manuscript_hash')!r}, expected {expected_manuscript_hash!r}"
        )
    snapshot_hashes = quality_eval.get("audit_snapshot_hashes")
    if isinstance(snapshot_hashes, dict):
        expected_repro = f"sha256:{_sha256_jsonable(reproducibility)}"
        expected_fidelity = f"sha256:{_sha256_jsonable(fidelity)}"
        if snapshot_hashes.get("reproducibility") != expected_repro:
            raise ValueError(f"quality-eval input is stale for the current reproducibility audit: {quality_eval_path}")
        if snapshot_hashes.get("fidelity") != expected_fidelity:
            raise ValueError(f"quality-eval input is stale for the current fidelity audit: {quality_eval_path}")


def write_quality_loop_plan(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    accept_mixed_provenance: bool = False,
    quality_eval_input_path: str | Path | None = None,
    append_history: bool = True,
) -> tuple[Path, dict[str, Any]]:
    fidelity_payload = run_fidelity_audit(cwd)
    fidelity_path = artifact_path(cwd, "fidelity.audit.json")
    write_json(fidelity_path, fidelity_payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(fidelity_path)
    save_session(cwd, state)
    write_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    reproducibility_payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    if quality_eval_input_path:
        quality_eval_path = Path(quality_eval_input_path).resolve()
        loaded_quality_eval = read_json(quality_eval_path)
        if not isinstance(loaded_quality_eval, dict):
            raise ValueError(f"quality-eval input is not a JSON object: {quality_eval_path}")
        state_for_eval = load_session(cwd)
        _validate_quality_eval_input(
            loaded_quality_eval,
            state=state_for_eval,
            reproducibility=reproducibility_payload,
            fidelity=fidelity_payload,
            quality_eval_path=quality_eval_path,
        )
        quality_eval = loaded_quality_eval
    else:
        quality_eval = build_quality_eval(
            cwd,
            quality_mode=quality_mode,
            require_live_verification=require_live_verification,
            max_iterations=max_iterations,
            reproducibility=reproducibility_payload,
            fidelity=fidelity_payload,
        )
        quality_eval_path = artifact_path(cwd, "quality-eval.json")
        write_json(quality_eval_path, quality_eval)
    payload = build_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval=quality_eval,
        quality_eval_path=quality_eval_path,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "qa-loop.plan.json")
    write_json(path, payload)
    if append_history:
        append_quality_loop_history(
            cwd,
            quality_eval,
            verdict=payload.get("verdict"),
            plan_path=path,
            quality_eval_path=quality_eval_path,
            event_type="qa_loop_plan",
            consumes_budget=False,
        )
    state = load_session(cwd)
    state.notes.append(f"QA loop plan recorded: {path.name}")
    save_session(cwd, state)
    return path, payload
