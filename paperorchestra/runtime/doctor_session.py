from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session


def build_session_recovery_hint(cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd or ".").resolve()
    try:
        state = load_session(root)
    except Exception as exc:
        return {
            "status": "missing",
            "detail": str(exc),
            "next_commands": ["paperorchestra init --idea ... --experimental-log ... --template ... --guidelines ..."],
        }

    artifacts = state.artifacts
    next_commands: list[str] = []
    notes: list[str] = []

    if artifacts.compiled_pdf and artifacts.paper_full_tex:
        status = "ok"
        notes.append("Session has a manuscript and compiled PDF artifact.")
    elif state.current_phase in {"complete", "draft_complete"}:
        status = "ok"
        notes.append("Session has reached a terminal usable draft state.")
    elif not artifacts.paper_full_tex:
        status = "actionable"
        next_commands.append("paperorchestra run --provider shell --discovery-mode search-grounded")
        notes.append("The phase-level commands are intentionally not public; use the full pipeline or write-sections once planning/citations exist.")
    elif state.current_phase == "blocked":
        status = "blocked"
        next_commands.extend(
            [
                "paperorchestra status --json",
                "paperorchestra critique --provider shell",
                "paperorchestra qa-loop-step --provider shell",
            ]
        )
        notes.append("Inspect latest validation/review artifacts before retrying refinement.")
    else:
        status = "actionable"
        next_commands.extend(["paperorchestra status --json", "paperorchestra run --provider shell"])

    if artifacts.latest_verification_errors_json:
        notes.append(f"Live verification errors recorded at: {artifacts.latest_verification_errors_json}")
    if artifacts.latest_runtime_parity_json:
        notes.append(f"Runtime parity report available at: {artifacts.latest_runtime_parity_json}")
    if artifacts.latest_reproducibility_json:
        notes.append(f"Reproducibility audit available at: {artifacts.latest_reproducibility_json}")

    return {
        "status": status,
        "session_id": state.session_id,
        "current_phase": state.current_phase,
        "active_artifact": state.active_artifact,
        "next_commands": next_commands,
        "notes": notes,
    }
