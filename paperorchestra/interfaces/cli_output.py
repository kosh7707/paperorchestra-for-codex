from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.session import run_dir
from paperorchestra.orchestra.scorecard import render_scorecard_summary


def path_or_missing(value: str | None) -> str:
    return value if value else "missing"


def status_summary_lines(cwd: Path, payload: dict[str, Any]) -> list[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    recovery = payload.get("session_recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    artifact_dir = (
        Path(str(artifacts.get("paper_full_tex"))).resolve().parent
        if artifacts.get("paper_full_tex")
        else run_dir(cwd, str(payload["session_id"])) / "artifacts"
    )
    lines = [
        f"Session: {payload['session_id']}",
        f"Phase: {payload['current_phase']}",
        f"Plan gate: {_status_label(payload.get('plan_gate'))}",
        f"Planning artifacts: {_status_label(payload.get('planning_artifacts'))}",
        f"Paper skeleton: {_status_label(payload.get('paper_skeleton'))}",
        "",
        "Main files:",
        f"  TeX: {path_or_missing(artifacts.get('paper_full_tex'))}",
        f"  PDF: {path_or_missing(artifacts.get('compiled_pdf'))}",
        f"  Review: {path_or_missing(artifacts.get('latest_review_json'))}",
        f"  Artifact directory: {artifact_dir}",
        "",
        "Next:",
    ]
    next_commands = recovery.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(f"  {command}" for command in next_commands)
    elif not artifacts.get("compiled_pdf"):
        lines.extend(
            [
                "  paperorchestra environment --summary",
                "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile",
            ]
        )
    else:
        lines.append("  paperorchestra export-current --output ./paperorchestra-output")
    return lines


def _status_label(value: Any) -> str:
    if not isinstance(value, dict):
        return "unknown"
    status = value.get("status") or value.get("reason") or "unknown"
    detail = value.get("reason") if value.get("status") else value.get("approval_state")
    return f"{status} ({detail})" if detail and detail != status else str(status)


def ok_warn(value: bool) -> str:
    return "OK" if value else "WARN"


def environment_summary_lines(payload: dict[str, Any]) -> list[str]:
    package_context = payload.get("package_context") if isinstance(payload.get("package_context"), dict) else {}
    profiles = payload.get("readiness_profiles") if isinstance(payload.get("readiness_profiles"), list) else []
    mcp_health = payload.get("paperorchestra_mcp_health") if isinstance(payload.get("paperorchestra_mcp_health"), dict) else {}
    mcp_config = mcp_health.get("config") if isinstance(mcp_health.get("config"), dict) else {}
    mcp_server = mcp_health.get("server") if isinstance(mcp_health.get("server"), dict) else {}
    mcp_attachment = (
        mcp_health.get("active_session_attachment")
        if isinstance(mcp_health.get("active_session_attachment"), dict)
        else {}
    )

    lines = [
        "PaperOrchestra environment summary",
        "",
        "Package:",
        f"  Python: {package_context.get('python_executable', 'unknown')}",
        f"  Package root: {package_context.get('package_root', 'unknown')}",
        "",
        "Readiness:",
    ]
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        ready = bool(profile.get("ready"))
        lines.append(f"  {ok_warn(ready)} {profile.get('name')}: {profile.get('status')}")
        missing = profile.get("missing")
        if isinstance(missing, list) and missing:
            lines.append(f"    missing: {'; '.join(str(item) for item in missing[:2])}")
    lines.extend(
        [
            "",
            "MCP:",
            f"  {ok_warn(bool(mcp_config.get('registered')))} config registered: {mcp_config.get('registered', False)}",
            f"  {ok_warn(bool(mcp_server.get('ok')))} stdio server health: {mcp_server.get('ok', False)}",
            f"  active Codex session attachment: not checked ({mcp_attachment.get('detail', 'cannot be verified from CLI')})",
            "",
            "Next:",
            "  paperorchestra status --summary",
            "  paperorchestra doctor",
        ]
    )
    return lines


def orchestrator_summary_lines(payload: dict[str, Any]) -> list[str]:
    actions = payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else []
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    first_action = actions[0].get("action_type") if actions and isinstance(actions[0], dict) else "none"
    return [
        "PaperOrchestra orchestrator state",
        render_scorecard_summary(scorecard) if scorecard else "Score: unscored",
        f"Readiness: {readiness.get('label', 'unknown')}",
        f"Next action: {first_action}",
    ]


def print_orchestrator_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    state_payload = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    lines: list[str] = []
    if isinstance(payload.get("execution_record"), dict):
        execution_record = payload["execution_record"]
        lines.extend(
            [
                f"Execution: {payload.get('execution', 'unknown')}",
                f"Action taken: {payload.get('action_taken', 'none')}",
                f"Execution status: {execution_record.get('status', 'unknown')}",
                f"Adapter: {execution_record.get('adapter', 'unknown')}",
                f"Reason: {execution_record.get('reason', 'unknown')}",
                f"State rebuild required: {execution_record.get('state_rebuild_required', 'unknown')}",
                "",
            ]
        )
    lines.extend(orchestrator_summary_lines(state_payload))
    print("\n".join(lines))
