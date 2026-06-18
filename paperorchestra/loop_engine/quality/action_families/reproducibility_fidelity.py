from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.policy import QA_LOOP_SUPPORTED_HANDLER_CODES


def _fidelity_actions(fidelity: dict[str, Any]) -> list[dict[str, Any]]:
    critical_commands = {
        "verified_citation_lane": ["paperorchestra run --provider shell --discovery-mode search-grounded", "paperorchestra quality-gate --no-fail-on-block"],
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
