from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.policy import QA_LOOP_SUPPORTED_HANDLER_CODES


def _mode_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    reasons = [str(reason) for reason in reproducibility.get("blocking_reasons") or []]
    if any("Provider was mock" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="provider-mode:1",
                code="mock_provider",
                source=reproducibility.get("source_artifacts", {}).get("paper_full_tex"),
                target="run configuration",
                automation="human_needed",
                reason="Provider was mock; manuscript output is not a live factual draft.",
                suggested_commands=["paperorchestra run --provider shell --runtime-mode omx_native"],
                ralph_instruction="Do not continue quality claims on mock output; rerun with a real provider or mark the artifact as demo-only.",
            )
        )
    if any("Citation verification used mock mode" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:1",
                code="mock_verification",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="verification lane",
                automation="human_needed",
                reason="Citation verification used mock mode.",
                suggested_commands=["paperorchestra run --provider shell --discovery-mode search-grounded", "paperorchestra quality-gate --no-fail-on-block --require-live-verification"],
                ralph_instruction="Use live verification for claim-safe runs, or stop and record that only an offline demo is available.",
            )
        )
    if any("seed-only or curated metadata without live verification" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:2",
                code="incomplete_live_verification",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="verification lane",
                automation="human_needed",
                reason="The citation registry still contains seed-only or curated metadata entries after a required live verification pass.",
                suggested_commands=[
                    "paperorchestra run --provider shell --discovery-mode search-grounded --require-live-verification",
                    "paperorchestra quality-gate --no-fail-on-block --require-live-verification",
                ],
                ralph_instruction="Do not present citation provenance as fully live until every registry entry is live-verified or explicitly removed/scoped.",
            )
        )
    if any("mixed cited provenance" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="verification-mode:3",
                code="mixed_citation_provenance_requires_acceptance",
                source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
                target="citation provenance",
                automation="human_needed",
                reason="One or more cited references have mixed cited provenance rather than live verification.",
                suggested_commands=[
                    "paperorchestra qa-loop --accept-mixed-provenance",
                    "paperorchestra quality-gate --no-fail-on-block --require-live-verification",
                ],
                ralph_instruction=(
                    "Do not treat mixed cited provenance as fully live. Either replace the affected cited references "
                    "with live-verified sources or explicitly accept the mixed provenance with an operator-owned "
                    "acceptance artifact before final readiness."
                ),
            )
        )
    if any("Prompt trace artifacts are missing" in reason for reason in reasons):
        actions.append(
            _action(
                action_id="provenance:1",
                code="missing_prompt_trace",
                source=reproducibility.get("source_artifacts", {}).get("latest_prompt_trace_dir"),
                target="provenance",
                automation="human_needed",
                reason="Prompt traces are missing, so the generation cannot be audited.",
                suggested_commands=["paperorchestra run --provider shell --runtime-mode omx_native"],
                ralph_instruction="Rerun the affected generation stage with prompt tracing enabled before accepting the draft.",
            )
        )
    return actions


def _warning_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for reason in reproducibility.get("warning_reasons") or []:
        reason_text = str(reason)
        if "non-blocking validation warning" in reason_text:
            continue
        if "Latest compile report is not clean" in reason_text:
            actions.append(
                _action(
                    action_id="warning:compile",
                    code="compile_not_clean",
                    source=reproducibility.get("source_artifacts", {}).get("latest_compile_report_json"),
                    target="compile",
                    automation="automatic",
                    reason=reason_text,
                    suggested_commands=["paperorchestra compile", "paperorchestra quality-gate --no-fail-on-block"],
                    ralph_instruction="Re-run compilation and inspect the compile report before accepting the current manuscript.",
                )
            )
        elif "No lane manifests" in reason_text:
            actions.append(
                _action(
                    action_id="warning:lane-manifest",
                    code="missing_lane_manifests",
                    source=reproducibility.get("source_artifacts", {}).get("latest_lane_summary_json"),
                    target="provenance",
                    automation="human_needed",
                    reason=reason_text,
                    suggested_commands=["paperorchestra run --provider shell --runtime-mode omx_native"],
                    ralph_instruction="Rerun or reconstruct the session with lane manifests before making claim-safe assertions.",
                )
            )
        else:
            actions.append(
                _action(
                    action_id=f"warning:{len(actions)+1}",
                    code="unclassified_reproducibility_warning",
                    source=None,
                    target="audit",
                    automation="human_needed",
                    reason=reason_text,
                    suggested_commands=["paperorchestra quality-gate --no-fail-on-block"],
                    ralph_instruction="Classify this reproducibility warning before stopping the Ralph loop.",
                )
            )
    return actions


def _fidelity_actions(fidelity: dict[str, Any]) -> list[dict[str, Any]]:
    critical_commands = {
        "verified_citation_lane": ["paperorchestra run --provider shell --discovery-mode search-grounded", "paperorchestra run --provider shell --discovery-mode search-grounded", "paperorchestra quality-gate --no-fail-on-block"],
        "section_writing_pipeline": ["paperorchestra write-sections", "paperorchestra critique", "paperorchestra quality-gate --no-fail-on-block"],
        "submission_ready_output": ["paperorchestra compile", "paperorchestra quality-gate --no-fail-on-block"],
        "compile_environment_ready": ["paperorchestra environment --summary"],
        "runtime_parity": ["paperorchestra run --provider shell --runtime-mode omx_native"],
    }
    actions: list[dict[str, Any]] = []
    for check in fidelity.get("checks") or []:
        if not isinstance(check, dict):
            continue
        code = str(check.get("code") or "")
        status = str(check.get("status") or "")
        if status == "implemented" or code not in critical_commands:
            continue
        action_code = f"fidelity_{code}_{status}"
        automation = (
            "automatic"
            if code in {"verified_citation_lane", "section_writing_pipeline", "submission_ready_output"}
            and action_code in QA_LOOP_SUPPORTED_HANDLER_CODES
            else "human_needed"
        )
        actions.append(
            _action(
                action_id=f"fidelity:{len(actions)+1}",
                code=action_code,
                source=None,
                target=code,
                automation=automation,
                reason=f"Critical fidelity check {code} is {status}: {check.get('rationale')}",
                suggested_commands=critical_commands[code],
                ralph_instruction="Resolve this critical fidelity gap before allowing the quality loop to stop.",
            )
        )
    return actions
