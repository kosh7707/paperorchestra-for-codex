from __future__ import annotations

import shlex

from paperorchestra.loop_engine.quality.policy import QA_LOOP_SUPPORTED_HANDLER_CODES

QA_LOOP_EXECUTION_SCHEMA_VERSION = "qa-loop-execution/1"
QA_LOOP_BRIEF_FILENAME = "ralph-brief.md"
QA_LOOP_HANDOFF_FILENAME = "ralph-handoff.json"
MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME = "paper.full.tex.candidate-write.json"
OMX_TMUX_INJECT_MARKER = "[OMX_TMUX_INJECT]"
OMX_TMUX_INJECT_PROMPT = f"Continue from current mode state. {OMX_TMUX_INJECT_MARKER}"
EXIT_CODES = {
    "ready_for_human_finalization": 0,
    "continue": 10,
    "human_needed": 20,
    "failed": 30,
    "execution_error": 40,
}
TERMINAL_VERDICTS = {"ready_for_human_finalization", "human_needed", "failed"}
SUPPORTED_HANDLER_CODES = QA_LOOP_SUPPORTED_HANDLER_CODES
NON_SUPPORTED_CITATION_STATUSES = {
    "unsupported",
    "weakly_supported",
    "insufficient_evidence",
    "needs_manual_check",
    "metadata_only",
    "contradicted",
}


def _qa_loop_step_command(
    *,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    provider_command_env: str = "PAPERO_MODEL_CMD",
    citation_provider_command_env: str = "PAPERO_WEB_PROVIDER_CMD",
) -> str:
    args = [
        "paperorchestra",
        "qa-loop-step",
        "--quality-mode",
        quality_mode,
        "--max-iterations",
        str(max_iterations),
        "--provider",
        "shell",
        "--runtime-mode",
        "omx_native",
        "--strict-omx-native",
        "--require-compile",
        "--citation-evidence-mode",
        "web",
        "--provider-command",
        f"${provider_command_env}",
        "--citation-provider",
        "shell",
        "--citation-provider-command",
        f"${citation_provider_command_env}",
    ]
    if require_live_verification:
        args.append("--require-live-verification")
    if accept_mixed_provenance:
        args.append("--accept-mixed-provenance")
    return " ".join(shlex.quote(arg) if not arg.startswith("$") else f"\"{arg}\"" for arg in args)


def qa_loop_exit_code(verdict: str) -> int:
    return EXIT_CODES.get(verdict, EXIT_CODES["execution_error"])
