from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.manuscript.source_obligations import source_obligations_path
from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.action_families.figure_placeholder_actions import _generated_placeholder_figure_actions
from paperorchestra.loop_engine.quality.action_families.figure_review_actions import _figure_review_actions
from paperorchestra.loop_engine.quality.action_families.reproducibility_fidelity import _fidelity_actions
from paperorchestra.loop_engine.quality.action_families.reproducibility_mode import _mode_actions
from paperorchestra.loop_engine.quality.action_families.reproducibility_warnings import _warning_actions
from paperorchestra.loop_engine.quality.action_families.strict_content import _strict_content_actions
from paperorchestra.loop_engine.quality.action_families.validation_warnings import _validation_actions
from paperorchestra.loop_engine.quality.actions import _citation_actions, _dedupe_actions
from paperorchestra.loop_engine.quality.action_builders import _quality_eval_actions
from paperorchestra.loop_engine.quality.citation_support import _citation_support_path
from paperorchestra.loop_engine.quality.audit_snapshots import build_quality_audits
from paperorchestra.loop_engine.quality.eval import build_quality_eval
from paperorchestra.loop_engine.quality.plan_payload import QualityLoopPlanPayloadInput, build_quality_loop_plan_payload
from paperorchestra.loop_engine.quality.plan_sources import build_quality_eval_for_plan
from paperorchestra.loop_engine.quality.plan_verdict import _plan_verdict
from paperorchestra.loop_engine.quality.policy import DEFAULT_MAX_ITERATIONS
from paperorchestra.loop_engine.quality.mixed_provenance_acceptance import _mixed_provenance_acceptance


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
    reproducibility, fidelity = build_quality_audits(cwd, require_live_verification=require_live_verification)
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

    actions = _plan_actions(
        state=state,
        reproducibility=reproducibility,
        fidelity=fidelity,
        quality_eval_for_plan=quality_eval_for_plan,
        citation_support_review_path=citation_support_review_path,
        citation_review_identity=citation_review_identity,
    )
    verdict, verdict_rationale = _plan_verdict(
        quality_eval_for_plan,
        actions,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    operator_packet_path, operator_packet_sha = _operator_packet_identity(cwd)
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


def _plan_actions(
    *,
    state: Any,
    reproducibility: dict[str, Any],
    fidelity: dict[str, Any],
    quality_eval_for_plan: dict[str, Any],
    citation_support_review_path: Path,
    citation_review_identity: Any,
) -> list[dict[str, Any]]:
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
    return _dedupe_actions(detailed_actions + strict_fallback_actions)


def _operator_packet_identity(cwd: str | Path | None) -> tuple[Path, Any]:
    operator_packet_path = artifact_path(cwd, "operator_review_packet.json")
    operator_packet_sha = None
    if operator_packet_path.exists():
        try:
            packet_payload = read_json(operator_packet_path)
            if isinstance(packet_payload, dict):
                operator_packet_sha = packet_payload.get("packet_sha256")
        except Exception:
            operator_packet_sha = None
    return operator_packet_path, operator_packet_sha
