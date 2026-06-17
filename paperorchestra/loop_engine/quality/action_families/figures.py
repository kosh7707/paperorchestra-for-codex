from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.policy import FIGURE_REPAIR_CODES, MANUAL_REVIEW_CODES
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def _figure_review_actions(state: Any) -> list[dict[str, Any]]:
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


def _generated_placeholder_figure_actions(state: Any) -> list[dict[str, Any]]:
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
