from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action


def _append_figure_grounding_actions(actions: list[dict[str, Any]], figure_check: Any) -> None:
    if not isinstance(figure_check, dict):
        return

    issue_items = [
        item
        for item in figure_check.get("figures") or []
        if isinstance(item, dict) and item.get("failing_codes")
    ]
    if not issue_items:
        issue_items = [{"label": "figure grounding", "failing_codes": figure_check.get("failing_codes") or []}]

    for item in issue_items:
        label = str(item.get("label") or "figure grounding")
        section = str(item.get("section_title") or "")
        assets = ", ".join(str(asset) for asset in item.get("included_assets") or [] if str(asset).strip())
        context = str(item.get("nearby_reference_context") or "").strip()
        manifest = item.get("plot_manifest_match") if isinstance(item.get("plot_manifest_match"), dict) else {}
        for code in [str(code) for code in item.get("failing_codes") or [] if str(code).strip()]:
            target = f"{label}" + (f" in {section}" if section else "")
            detail = (
                (f" Assets: {assets}." if assets else "")
                + (f" Nearby context: {context[:180]}." if context else "")
                + (f" Manifest purpose/title: {manifest.get('purpose') or manifest.get('title')}." if manifest else "")
            )
            actions.append(
                _action(
                    action_id=f"quality-eval:figure-grounding:{code}:{len(actions)+1}",
                    code=code,
                    source=figure_check.get("path"),
                    target=target,
                    automation="human_needed",
                    reason=f"Figure-placement review failed for {target} with {code}; claim-safe readiness requires critic/operator judgment before changing visual evidence or captions.{detail}",
                    suggested_commands=[
                        "paperorchestra critique",
                        "paperorchestra answer-human-needed --answer <answer>",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction=(
                        "Do not route unsafe figure/caption grounding to automatic repair. Ask a figure-placement critic/operator to remove, "
                        "replace, or recaption the affected figure, then rerun review-figure-placement."
                    ),
                    why_not_automatic="Changing figure placement, captions, or visual evidence can alter paper meaning and requires figure-grounding critic/operator approval.",
                    approval_required_from="figure_placement_review_critic",
                )
            )
