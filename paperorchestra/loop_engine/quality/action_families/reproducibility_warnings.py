from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action


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
