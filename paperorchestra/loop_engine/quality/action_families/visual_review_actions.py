from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists

PAGE_LAYOUT_REVIEW_CODES = {"page_layout_review_missing", "page_layout_review_stale"}
PAGE_LAYOUT_RENDER_CODES = {"page_layout_render_failed", "page_layout_render_unavailable"}
VISUAL_REPAIR_BRIEF_CODES = {"visual_layout_repair_brief_needed"}
VISUAL_REPAIR_CANDIDATE_CODES = {"visual_layout_repair_candidate_needed"}
VISUAL_HUMAN_HANDOFF_CODES = {"visual_final_artwork_handoff"}


def _page_visual_review_actions(state: Any) -> list[dict[str, Any]]:
    paper_path = getattr(state.artifacts, "paper_full_tex", None)
    pdf_path = getattr(state.artifacts, "compiled_pdf", None)
    if not paper_path or not pdf_path:
        return []
    review_path = getattr(state.artifacts, "latest_page_layout_review_json", None)
    payload = _read_json_if_exists(review_path)
    if not isinstance(payload, dict):
        return [_review_refresh_action("page_layout_review_missing", review_path, pdf_path)]
    if _stale_review(state, payload):
        return [_review_refresh_action("page_layout_review_stale", review_path, pdf_path)]
    if _render_failed(payload):
        return [_render_failure_action(review_path, pdf_path, payload)]
    candidates = [item for item in payload.get("repair_candidates") or [] if isinstance(item, dict)]
    if not candidates:
        return []
    actions: list[dict[str, Any]] = []
    semi_auto = [candidate for candidate in candidates if candidate.get("automation") != "human_needed"]
    human_needed = [candidate for candidate in candidates if candidate.get("automation") == "human_needed"]
    if semi_auto:
        if not _fresh_repair_brief_exists(state, review_path):
            actions.append(_visual_repair_brief_action(state, semi_auto))
        elif not _fresh_repair_candidate_exists(state):
            actions.append(_visual_repair_candidate_action(state, semi_auto))
        else:
            actions.append(_visual_candidate_review_action(state, semi_auto))
    if human_needed:
        actions.append(_visual_handoff_action(state, human_needed))
    return actions


def _stale_review(state: Any, payload: dict[str, Any]) -> bool:
    current_sha = _file_sha256(getattr(state.artifacts, "paper_full_tex", None))
    current_pdf_sha = _file_sha256(getattr(state.artifacts, "compiled_pdf", None))
    return bool(
        (current_sha and payload.get("manuscript_sha256") != current_sha)
        or (current_pdf_sha and payload.get("compiled_pdf_sha256") != current_pdf_sha)
    )


def _render_failed(payload: dict[str, Any]) -> bool:
    render_status = payload.get("render_status") if isinstance(payload.get("render_status"), dict) else {}
    return str(render_status.get("status") or "").lower() in {"fail", "failed", "unavailable", "error"}


def _render_failure_reason(payload: dict[str, Any]) -> str:
    render_status = payload.get("render_status") if isinstance(payload.get("render_status"), dict) else {}
    reason = render_status.get("reason") or render_status.get("status") or "render evidence unavailable"
    return f"Rendered PDF page evidence is unavailable or failed ({reason}); rerun visual-audit only after render prerequisites are restored."


def _render_failure_code(payload: dict[str, Any]) -> str:
    render_status = payload.get("render_status") if isinstance(payload.get("render_status"), dict) else {}
    return "page_layout_render_unavailable" if render_status.get("status") == "unavailable" else "page_layout_render_failed"


def _fresh_repair_brief_exists(state: Any, review_path: str | Path | None) -> bool:
    brief_path = getattr(state.artifacts, "latest_visual_repair_brief_json", None)
    payload = _read_json_if_exists(brief_path)
    if not isinstance(payload, dict):
        return False
    expected_review_sha = _file_sha256(review_path)
    return bool(expected_review_sha and payload.get("source_review_sha256") == expected_review_sha)


def _fresh_repair_candidate_exists(state: Any) -> bool:
    brief_path = getattr(state.artifacts, "latest_visual_repair_brief_json", None)
    candidate_path = getattr(state.artifacts, "latest_visual_repair_candidate_json", None)
    payload = _read_json_if_exists(candidate_path)
    if not isinstance(payload, dict):
        return False
    expected_brief_sha = _file_sha256(brief_path)
    return bool(expected_brief_sha and payload.get("source_brief_sha256") == expected_brief_sha)


def _review_refresh_action(
    code: str,
    review_path: str | Path | None,
    pdf_path: str | Path,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    quoted_pdf = shlex.quote(str(pdf_path))
    return _action(
        action_id=f"page-layout:{code}",
        code=code,
        source=str(review_path) if review_path else None,
        target="rendered PDF page layout",
        automation="automatic",
        reason=reason or "Page-level visual/layout audit is missing or stale for the current compiled PDF.",
        suggested_commands=[f"paperorchestra visual-audit --pdf {quoted_pdf}", "paperorchestra qa-loop --quality-mode claim_safe"],
        ralph_instruction="Regenerate page-layout review from the compiled PDF before accepting or repairing visual/layout claims.",
    )


def _render_failure_action(review_path: str | Path | None, pdf_path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    quoted_pdf = shlex.quote(str(pdf_path))
    return _action(
        action_id=f"page-layout:{_render_failure_code(payload)}",
        code=_render_failure_code(payload),
        source=str(review_path) if review_path else None,
        target="rendered PDF page evidence",
        automation="automatic",
        reason=_render_failure_reason(payload),
        suggested_commands=[f"paperorchestra visual-audit --pdf {quoted_pdf}", "paperorchestra qa-loop --quality-mode claim_safe"],
        ralph_instruction=(
            "Treat this as a render-evidence blocker, not a missing-review blocker: restore PDF/render prerequisites, "
            "rerun page visual audit, and do not accept rendered layout claims until page images exist."
        ),
    )


def _visual_repair_brief_action(state: Any, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return _action(
        action_id="visual-layout:repair-brief",
        code="visual_layout_repair_brief_needed",
        source=getattr(state.artifacts, "latest_page_layout_review_json", None),
        target="page visual/layout repair candidates",
        automation="semi_auto",
        reason=f"{len(candidates)} machine-actionable page visual/layout finding(s) need a repair brief before handoff.",
        suggested_commands=[
            "paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1",
            "paperorchestra visual-audit --findings-json page-visual-findings.json",
        ],
        ralph_instruction=(
            "Take ownership of visual repair: generate visual_repair_brief.json and route machine-actionable layout fixes "
            "back into PaperOrchestra/Critic, not the user. Escalate only final artwork or aesthetic preference decisions."
        ),
        approval_required_from="visual_layout_critic",
    )


def _visual_repair_candidate_action(state: Any, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return _action(
        action_id="visual-layout:repair-candidate",
        code="visual_layout_repair_candidate_needed",
        source=getattr(state.artifacts, "latest_visual_repair_brief_json", None),
        target="page visual/layout repair candidate",
        automation="semi_auto",
        reason=f"{len(candidates)} visual repair brief action(s) need concrete PaperOrchestra repair candidates before human handoff.",
        suggested_commands=[
            "paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1",
            "Apply the selected visual_repair_candidate.json instruction, recompile, then rerun paperorchestra visual-audit.",
        ],
        ralph_instruction=(
            "Generate visual_repair_candidate.json from the repair brief. The candidate must specify a bounded TeX/table/figure "
            "layout strategy plus claim/location/caption guards before the user is asked to decide."
        ),
        approval_required_from="visual_layout_critic",
    )


def _visual_candidate_review_action(state: Any, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return _action(
        action_id="visual-layout:candidate-review",
        code="visual_repair_candidate_review_needed",
        source=getattr(state.artifacts, "latest_visual_repair_candidate_json", None),
        target="visual repair candidate review",
        automation="human_needed",
        reason=(
            f"{len(candidates)} visual finding(s) remain after PaperOrchestra produced a repair candidate; "
            "the next decision is to apply, reject, or revise that candidate."
        ),
        suggested_commands=[
            "Review visual_repair_candidate.json, apply the selected bounded repair, recompile, then rerun paperorchestra visual-audit.",
        ],
        ralph_instruction=(
            "Do not merely tell the user the visual is bad. Present the generated candidate and the exact apply/reject/revise decision."
        ),
        why_not_automatic="Applying arbitrary layout/caption/table edits can change claim meaning; a candidate has been produced, but adoption requires approval or a bounded edit command.",
        approval_required_from="author_or_visual_layout_critic",
    )


def _visual_handoff_action(state: Any, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    targets = ", ".join(str(item.get("target") or item.get("code")) for item in candidates[:3])
    return _action(
        action_id="visual-layout:human-final-artwork",
        code="visual_final_artwork_handoff",
        source=getattr(state.artifacts, "latest_page_layout_review_json", None),
        target=targets or "final visual artifacts",
        automation="human_needed",
        reason="One or more visual findings require final artwork, semantic visual evidence judgment, or human aesthetic preference.",
        suggested_commands=["Provide human-authored final artwork or an explicit design decision, then rerun paperorchestra visual-audit."],
        ralph_instruction="Stop before pretending AI draft artwork is final; prepare exact artwork/design decisions needed from the author.",
        why_not_automatic="Final artwork and aesthetic preference are not safe to auto-commit as scholarly evidence.",
        approval_required_from="author_visual_owner",
    )
