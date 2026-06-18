from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.action_families.validation_policy import (
    _automation_for_issue,
    _claim_safety_approval,
    _commands_for_validation_issue,
    _target_section_from_stage,
)
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists


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
