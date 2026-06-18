from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.state import (
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_HANDOFF_FILENAME,
)


def handoff_payload(
    *,
    cwd: str | Path | None,
    cwd_path: Path,
    state: Any,
    brief_path: Path,
    prd_path: Path,
    canonical_prd_path: Path,
    canonical_test_spec_path: Path,
    step_cmd: str,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    evidence_root: str | Path | None,
    artifact_path_fn,
) -> dict[str, Any]:
    handoff_path = artifact_path_fn(cwd, QA_LOOP_HANDOFF_FILENAME)
    evidence_root_path = Path(evidence_root).resolve() if evidence_root else cwd_path
    suggested_command = "omx ralph --prd \"$(cat " + str(brief_path) + ")\""
    return {
        "schema_version": "paperorchestra-ralph-handoff/1",
        "session_id": state.session_id,
        "brief_path": str(brief_path),
        "prd_path": str(prd_path),
        "canonical_prd_path": str(canonical_prd_path),
        "canonical_test_spec_path": str(canonical_test_spec_path),
        "handoff_path": str(handoff_path),
        "suggested_command": suggested_command,
        "operator_transcript_command": "script -q -f transcript/ralph-operator.typescript -c "
        + shlex.quote(suggested_command),
        "argv": ["omx", "ralph", "--prd", brief_path.read_text(encoding="utf-8")],
        "hook_contract": hook_contract(),
        "execution_contract": execution_contract(
            step_cmd=step_cmd,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
        ),
        "evidence_contract": evidence_contract(evidence_root_path),
    }


def hook_contract() -> dict[str, Any]:
    return {
        "marker": OMX_TMUX_INJECT_MARKER,
        "continuation_prompt": OMX_TMUX_INJECT_PROMPT,
        "allowed_mode": "ralph",
        "continuation_exit_code": 10,
        "terminal_exit_codes": {
            "ready_for_human_finalization": 0,
            "human_needed": 20,
            "failed": 30,
            "execution_error": 40,
        },
    }


def execution_contract(
    *,
    step_cmd: str,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
) -> dict[str, Any]:
    return {
        "step_command": step_cmd,
        "ralph_required": quality_mode == "claim_safe",
        "critic_required": quality_mode == "claim_safe",
        "citation_integrity_gate_required": quality_mode == "claim_safe",
        "human_needed_cycle_policy": {
            "requested_cycles": max_iterations,
            "observed_cycles": None,
            "counter_source": ".paper-orchestra/qa-loop-history.jsonl",
        },
        "requires_papero_model_cmd": True,
        "requires_papero_web_provider_cmd": True,
        "requires_web_search_provider": True,
        "quality_mode": quality_mode,
        "max_iterations": max_iterations,
        "require_live_verification": require_live_verification,
        "accept_mixed_provenance": accept_mixed_provenance,
    }


def evidence_contract(evidence_root_path: Path) -> dict[str, Any]:
    return {
        "evidence_root": str(evidence_root_path),
        "operator_transcript": str(evidence_root_path / "transcript" / "ralph-operator.typescript"),
        "qa_loop_execution_glob": ".paper-orchestra/qa-loop-execution.iter-*.json",
        "qa_loop_history": ".paper-orchestra/qa-loop-history.jsonl",
        "readable_summary_files": [
            "READ_ME_FIRST.md",
            "readable/timeline.md",
            "readable/commands.md",
            "readable/verdict.md",
            "readable/qa-loop-summary.md",
        ],
    }
