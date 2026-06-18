from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.source_obligations import source_obligations_path

from .action_core import _action
from .action_families.figures import _figure_review_actions, _generated_placeholder_figure_actions
from .action_families.reproducibility import _fidelity_actions, _mode_actions, _warning_actions
from .action_families.validation import _strict_content_actions, _validation_actions
from .actions import _citation_actions, _dedupe_actions
from .action_builders import _quality_eval_actions
from .citation_support import _citation_support_path
from .audit_snapshots import build_quality_audits, refresh_quality_audit_artifacts
from .eval import build_quality_eval
from .eval_input import validate_quality_eval_input as _validate_quality_eval_input
from .provenance import _mixed_provenance_acceptance
from .history_writer import append_quality_loop_history
from .plan_payload import QualityLoopPlanPayloadInput, build_quality_loop_plan_payload
from .plan_logic import _plan_verdict
from .plan_sources import build_quality_eval_for_plan
from .policy import (
    DEFAULT_MAX_ITERATIONS,
)


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
    reproducibility, fidelity = build_quality_audits(
        cwd,
        require_live_verification=require_live_verification,
    )
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
    state, reproducibility_payload, fidelity_payload = refresh_quality_audit_artifacts(
        cwd,
        require_live_verification=require_live_verification,
    )
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
    state.notes.append(f"Quality eval recorded: {path.name}")
    save_session(cwd, state)
    if append_history:
        append_quality_loop_history(cwd, payload, quality_eval_path=path, event_type="quality_eval", consumes_budget=False)
    return path, payload



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
    state, reproducibility_payload, fidelity_payload = refresh_quality_audit_artifacts(
        cwd,
        require_live_verification=require_live_verification,
    )
    if quality_eval_input_path:
        quality_eval_path = Path(quality_eval_input_path).resolve()
        loaded_quality_eval = read_json(quality_eval_path)
        if not isinstance(loaded_quality_eval, dict):
            raise ValueError(f"quality-eval input is not a JSON object: {quality_eval_path}")
        _validate_quality_eval_input(
            loaded_quality_eval,
            state=state,
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
    state.notes.append(f"QA loop plan recorded: {path.name}")
    save_session(cwd, state)
    return path, payload
