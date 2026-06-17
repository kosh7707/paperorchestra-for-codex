from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from .policy import (
    AUTO_REPAIR_CODES,
    FIGURE_REPAIR_CODES,
    MANUAL_REVIEW_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    SEMI_AUTO_REPAIR_CODES,
)
from .utils import _file_sha256, _read_json_if_exists


def _action(
    *,
    action_id: str,
    code: str,
    source: str | None,
    reason: str,
    automation: str,
    target: str | None = None,
    suggested_commands: list[str] | None = None,
    ralph_instruction: str | None = None,
    why_not_automatic: str | None = None,
    approval_required_from: str | None = None,
    preconditions: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": action_id,
        "code": code,
        "source": source,
        "target": target,
        "automation": automation,
        "reason": reason,
        "suggested_commands": suggested_commands or [],
        "ralph_instruction": ralph_instruction or reason,
        "preconditions": preconditions or ["tier_1_structural must remain pass"],
    }
    if why_not_automatic:
        payload["why_not_automatic"] = why_not_automatic
    if approval_required_from:
        payload["approval_required_from"] = approval_required_from
    return payload

def _automation_for_issue(code: str) -> str:
    if code in SEMI_AUTO_REPAIR_CODES:
        return "semi_auto"
    if code in AUTO_REPAIR_CODES:
        return "automatic"
    return "human_needed"

def _target_section_from_stage(stage: str | None) -> str | None:
    if stage == "intro_related":
        return "Introduction, Related Work"
    if stage == "section_writing":
        return "full manuscript"
    if stage == "refinement":
        return "current manuscript"
    return None

def _section_arg(target: str | None) -> str:
    if not target or target in {"full manuscript", "current manuscript"}:
        return ""
    return f" --only-sections {shlex.quote(target)}"

def _commands_for_validation_issue(code: str, target: str | None) -> list[str]:
    section_arg = _section_arg(target)
    if code == "unsupported_comparative_claim":
        return [
            "paperorchestra quality-gate --no-fail-on-block",
            "paperorchestra critique",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
            "paperorchestra qa-loop --quality-mode claim_safe",
        ]
    if code in {"unknown_citation_keys", "citation_coverage_insufficient"}:
        return [
            "paperorchestra run --provider shell --discovery-mode search-grounded",
            "paperorchestra critique",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code == "numeric_grounding_mismatch":
        return [
            "paperorchestra quality-gate --no-fail-on-block",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code in {"expected_section_missing", "expected_section_too_shallow"}:
        return [
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra critique",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    if code == "plot_plan_not_reflected":
        return [
            "paperorchestra run --provider shell",
            f"paperorchestra write-sections{section_arg}",
            "paperorchestra critique",
            "paperorchestra quality-gate --no-fail-on-block",
        ]
    return ["paperorchestra quality-gate --no-fail-on-block"]

def _claim_safety_approval(code: str) -> tuple[str | None, str | None]:
    if code == "unsupported_comparative_claim":
        return (
            "Softening or deleting a comparative claim changes substantive paper content; a citation-support critic or human must approve before committing it.",
            "citation_support_critic",
        )
    if code == "numeric_grounding_mismatch":
        return (
            "Changing numeric prose can alter empirical claims; the rewrite must be checked against the experimental log.",
            "claim_safety_critic",
        )
    if code == "citation_coverage_insufficient":
        return (
            "Adding citation coverage is only safe from the verified pool; new citations must follow discovery -> verification -> registry.",
            "citation_support_critic",
        )
    return (None, None)

def _validation_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for report in reproducibility.get("validation_warning_reports") or []:
        source = report.get("path")
        payload = _read_json_if_exists(source)
        if not isinstance(payload, dict):
            continue
        stage = payload.get("stage")
        target = _target_section_from_stage(stage)
        for issue in payload.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "unknown_validation_issue")
            severity = str(issue.get("severity") or "warning")
            if severity not in {"warning", "error"}:
                continue
            key = (code, stage if isinstance(stage, str) else None, source if isinstance(source, str) else None)
            if key in seen:
                continue
            seen.add(key)
            automation = _automation_for_issue(code)
            why, approval = _claim_safety_approval(code)
            actions.append(
                _action(
                    action_id=f"validation:{len(actions)+1}",
                    code=code,
                    source=source,
                    target=target,
                    automation=automation,
                    reason=str(issue.get("message") or f"Validation issue {code}"),
                    suggested_commands=_commands_for_validation_issue(code, target),
                    ralph_instruction=(
                        "Produce a candidate rewrite only from existing evidence; do not add new facts or citations outside the verified registry."
                        if automation == "semi_auto"
                        else "Rewrite only the affected section when possible; preserve validated citations, numbers, labels, and prior accepted structure."
                        if automation == "automatic"
                        else "Escalate this validation issue to a human reviewer before changing manuscript content."
                    ),
                    why_not_automatic=why,
                    approval_required_from=approval,
                )
            )
    return actions

def _strict_content_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "strict_content_gate")
        source = issue.get("source") if isinstance(issue.get("source"), str) else None
        key = (code, source)
        if key in seen:
            continue
        seen.add(key)
        kind = issue.get("kind")
        why = None
        approval = None
        if code in {"validation_report_missing", "validation_report_stale"}:
            automation = "automatic"
            commands = [
                "paperorchestra quality-gate --no-fail-on-block",
                "paperorchestra quality-gate --no-fail-on-block",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ]
            instruction = (
                "Regenerate a validation report for the current manuscript before attempting content repair; do not act on stale validation warnings."
            )
        elif code in {"figure_placement_review_missing", "figure_placement_review_stale"}:
            automation = "automatic"
            commands = [
                "paperorchestra critique",
                "paperorchestra quality-gate --no-fail-on-block",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ]
            instruction = (
                "Regenerate figure-placement review for the current manuscript before moving figures or rewriting figure references."
            )
        elif kind in {"figure_placement_warning", "figure_placement_failure"}:
            automation = "human_needed"
            commands = [
                "paperorchestra critique",
                "paperorchestra write-sections --only-sections \"Implementation Results\"",
                "paperorchestra quality-gate --no-fail-on-block",
            ]
            instruction = (
                "Prepare a targeted figure-grounding decision for a human reviewer; do not auto-edit figure placement, captions, or visual evidence from the quality loop."
            )
            why = "Figure placement/caption changes affect narrative flow, visual evidence, and claim meaning; PaperOrchestra can flag them but cannot safely auto-commit final placement."
            approval = "figure_placement_review_critic"
        else:
            automation = _automation_for_issue(code)
            commands = _commands_for_validation_issue(code, None)
            instruction = (
                "Produce a candidate claim-safe rewrite grounded only in existing logs/citations; require second-critic approval before commit."
                if automation == "semi_auto"
                else "Rewrite the affected structural issue without adding new claims."
                if automation == "automatic"
                else "Escalate this strict content issue to a human reviewer."
            )
            why, approval = _claim_safety_approval(code)
        actions.append(
            _action(
                action_id=f"strict-content:{len(actions)+1}",
                code=code,
                source=source,
                target=issue.get("stage") if isinstance(issue.get("stage"), str) else None,
                automation=automation,
                reason=str(issue.get("message") or f"Strict content gate issue {code}"),
                suggested_commands=commands,
                ralph_instruction=instruction,
                why_not_automatic=why,
                approval_required_from=approval,
            )
        )
    return actions

def _citation_actions(reproducibility: dict[str, Any]) -> list[dict[str, Any]]:
    issues = reproducibility.get("citation_artifact_issues") or []
    if not issues:
        return []
    return [
        _action(
            action_id="citation-artifacts:1",
            code="citation_artifact_health",
            source=reproducibility.get("source_artifacts", {}).get("citation_registry_json"),
            target="citation lane",
            automation="automatic",
            reason="Final citation artifacts are empty, malformed, or inconsistent: " + "; ".join(str(item) for item in issues),
            suggested_commands=[
                "paperorchestra run --provider shell --discovery-mode search-grounded",
                "paperorchestra run --provider shell --discovery-mode search-grounded",
                "paperorchestra quality-gate --no-fail-on-block",
            ],
            ralph_instruction="Rebuild or re-import the citation lane before attempting more prose refinement; do not accept a manuscript with empty or malformed citation artifacts.",
        )
    ]

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

def _figure_review_actions(state) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(state.artifacts.latest_figure_placement_review_json)
    if not isinstance(payload, dict):
        return []
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        return []
    actions: list[dict[str, Any]] = []
    for figure in payload.get("figures") or []:
        if not isinstance(figure, dict):
            continue
        failing_codes = [str(code) for code in figure.get("failing_codes") or []]
        warning_codes = [str(code) for code in figure.get("warning_codes") or []]
        actionable_failures = [code for code in failing_codes if code.strip()]
        actionable_warnings = [code for code in warning_codes if code in FIGURE_REPAIR_CODES or code in MANUAL_REVIEW_CODES]
        actionable = actionable_failures + actionable_warnings
        if not actionable:
            continue
        label = str(figure.get("label") or "unknown")
        section = figure.get("section_title") if isinstance(figure.get("section_title"), str) else None
        included_assets = ", ".join(str(item) for item in figure.get("included_assets") or [] if str(item).strip())
        manifest = figure.get("plot_manifest_match") if isinstance(figure.get("plot_manifest_match"), dict) else {}
        context = str(figure.get("nearby_reference_context") or "").strip()
        for code in actionable:
            is_failure = code in actionable_failures
            actions.append(
                _action(
                    action_id=f"figure:{len(actions)+1}",
                    code=code,
                    source=state.artifacts.latest_figure_placement_review_json,
                    target=label,
                    automation="human_needed",
                    reason=(
                        f"Figure {label} has {'grounding failure' if is_failure else 'placement warning'} {code}."
                        + (f" Section: {section}." if section else "")
                        + (f" Assets: {included_assets}." if included_assets else "")
                        + (f" Nearby context: {context[:180]}." if context else "")
                        + (f" Manifest purpose/title: {manifest.get('purpose') or manifest.get('title')}." if manifest else "")
                    ),
                    suggested_commands=[
                        "paperorchestra critique",
                        f"paperorchestra write-sections --only-sections {shlex.quote(section or 'Implementation Results')}",
                        "paperorchestra quality-gate --no-fail-on-block",
                    ],
                    ralph_instruction=(
                        "Stop automatic figure editing. Prepare a bounded figure-grounding decision: remove/quarantine nontechnical figures, "
                        "rewrite process captions into scholarly captions, or ask the operator to supply final artwork."
                        if is_failure
                        else "Stop automatic figure-layout editing and request human/critic review for figure redistribution, removal, or final artwork placement."
                    ),
                    why_not_automatic="Figure placement and caption grounding affect narrative meaning and visual evidence; PaperOrchestra can flag them but cannot safely auto-commit final placement.",
                    approval_required_from="figure_placement_review_critic",
                )
            )
    return actions

def _generated_placeholder_figure_actions(state) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(state.artifacts.plot_assets_json)
    if not isinstance(payload, dict) or not state.artifacts.paper_full_tex or not Path(state.artifacts.paper_full_tex).exists():
        return []
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8", errors="replace")
    placeholder_assets: list[str] = []
    for asset in payload.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("asset_kind") != "generated_placeholder" and asset.get("review_status") != "human_final_artwork_required":
            continue
        references = [
            asset.get("latex_snippet_path"),
            asset.get("latex_path"),
            asset.get("filename"),
        ]
        if any(isinstance(ref, str) and ref and ref in latex for ref in references):
            placeholder_assets.append(str(asset.get("figure_id") or asset.get("filename") or "generated_placeholder"))
    if not placeholder_assets:
        return []
    return [
        _action(
            action_id="figure:final-artwork",
            code="final_figure_assets_non_reviewable",
            source=state.artifacts.plot_assets_json,
            target="final figures",
            automation="human_needed",
            reason="Generated placeholder figure assets are still used in the manuscript, so the artifact is not reviewable until human final artwork replaces or removes them.",
            suggested_commands=[
                "Replace generated placeholder assets with human-authored final figures, or remove/defer those figures.",
                "paperorchestra critique",
                "paperorchestra qa-loop --quality-mode claim_safe",
            ],
            ralph_instruction="Stop automatic paper packaging: placeholder figures are acceptable draft scaffolds but not review-ready evidence.",
            preconditions=["tier_1_structural must remain pass"],
        )
    ]

def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for action in actions:
        key = (str(action.get("code")), action.get("target"), action.get("source"))
        if key in seen:
            continue
        seen.add(key)
        action = dict(action)
        action["id"] = f"repair-{len(deduped)+1:02d}"
        deduped.append(action)
    return deduped
