from __future__ import annotations

import shlex
from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.policy import FIGURE_REPAIR_CODES, MANUAL_REVIEW_CODES
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def _figure_review_actions(state: Any) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(state.artifacts.latest_figure_placement_review_json)
    if not isinstance(payload, dict) or _stale_figure_review(state, payload):
        return []
    actions: list[dict[str, Any]] = []
    for figure in payload.get("figures") or []:
        if isinstance(figure, dict):
            actions.extend(_figure_actions(state, figure, start_index=len(actions) + 1))
    return actions


def _stale_figure_review(state: Any, payload: dict[str, Any]) -> bool:
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    return bool(current_sha and payload.get("manuscript_sha256") != current_sha)


def _figure_actions(state: Any, figure: dict[str, Any], *, start_index: int) -> list[dict[str, Any]]:
    actionable_failures = _figure_failing_codes(figure)
    actionable_warnings = _figure_warning_codes(figure)
    return [
        _figure_action(state, figure, code, is_failure=code in actionable_failures, index=start_index + offset)
        for offset, code in enumerate([*actionable_failures, *actionable_warnings])
    ]


def _figure_failing_codes(figure: dict[str, Any]) -> list[str]:
    return [str(code) for code in figure.get("failing_codes") or [] if str(code).strip()]


def _figure_warning_codes(figure: dict[str, Any]) -> list[str]:
    return [
        str(code)
        for code in figure.get("warning_codes") or []
        if code in FIGURE_REPAIR_CODES or code in MANUAL_REVIEW_CODES
    ]


def _figure_action(state: Any, figure: dict[str, Any], code: str, *, is_failure: bool, index: int) -> dict[str, Any]:
    label = str(figure.get("label") or "unknown")
    section = figure.get("section_title") if isinstance(figure.get("section_title"), str) else None
    return _action(
        action_id=f"figure:{index}",
        code=code,
        source=state.artifacts.latest_figure_placement_review_json,
        target=label,
        automation="human_needed",
        reason=_figure_action_reason(figure, label=label, section=section, code=code, is_failure=is_failure),
        suggested_commands=[
            "paperorchestra critique",
            f"paperorchestra write-sections --only-sections {shlex.quote(section or 'Implementation Results')}",
            "paperorchestra quality-gate --no-fail-on-block",
        ],
        ralph_instruction=_figure_ralph_instruction(is_failure=is_failure),
        why_not_automatic="Figure placement and caption grounding affect narrative meaning and visual evidence; PaperOrchestra can flag them but cannot safely auto-commit final placement.",
        approval_required_from="figure_placement_review_critic",
    )


def _figure_action_reason(figure: dict[str, Any], *, label: str, section: str | None, code: str, is_failure: bool) -> str:
    included_assets = ", ".join(str(item) for item in figure.get("included_assets") or [] if str(item).strip())
    manifest = figure.get("plot_manifest_match") if isinstance(figure.get("plot_manifest_match"), dict) else {}
    context = str(figure.get("nearby_reference_context") or "").strip()
    return (
        f"Figure {label} has {'grounding failure' if is_failure else 'placement warning'} {code}."
        + (f" Section: {section}." if section else "")
        + (f" Assets: {included_assets}." if included_assets else "")
        + (f" Nearby context: {context[:180]}." if context else "")
        + (f" Manifest purpose/title: {manifest.get('purpose') or manifest.get('title')}." if manifest else "")
    )


def _figure_ralph_instruction(*, is_failure: bool) -> str:
    if is_failure:
        return (
            "Stop automatic figure editing. Prepare a bounded figure-grounding decision: remove/quarantine nontechnical figures, "
            "rewrite process captions into scholarly captions, or ask the operator to supply final artwork."
        )
    return "Stop automatic figure-layout editing and request human/critic review for figure redistribution, removal, or final artwork placement."
