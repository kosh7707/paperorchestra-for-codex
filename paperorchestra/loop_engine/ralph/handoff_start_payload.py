from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS
from paperorchestra.loop_engine.ralph.handoff_brief import write_qa_loop_brief
from paperorchestra.loop_engine.ralph.state import (
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_HANDOFF_FILENAME,
    _qa_loop_step_command,
)


def build_ralph_start_payload(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_path: str | Path | None = None,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    evidence_root: str | Path | None = None,
    _write_brief_fn=write_qa_loop_brief,
    _load_session_fn=load_session,
    _write_json_fn=write_json,
    _artifact_path_fn=artifact_path,
    _step_command_fn=_qa_loop_step_command,
) -> dict[str, Any]:
    brief_path, brief = _write_brief_fn(
        cwd,
        output_path,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    state = _load_session_fn(cwd)
    cwd_path = Path(cwd or ".").resolve()
    step_cmd = _step_command_fn(
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    prd_path = _write_legacy_prd(
        cwd_path,
        state.session_id,
        brief_path,
        max_iterations=max_iterations,
        write_json_fn=_write_json_fn,
    )
    canonical_prd_path, canonical_test_spec_path = _write_plan_docs(
        cwd_path,
        state.session_id,
        brief_path=brief_path,
        step_cmd=step_cmd,
    )
    payload = _handoff_payload(
        cwd=cwd,
        cwd_path=cwd_path,
        state=state,
        brief_path=brief_path,
        prd_path=prd_path,
        canonical_prd_path=canonical_prd_path,
        canonical_test_spec_path=canonical_test_spec_path,
        step_cmd=step_cmd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        evidence_root=evidence_root,
        artifact_path_fn=_artifact_path_fn,
    )
    _write_json_fn(Path(payload["handoff_path"]), payload)
    return {**payload, "brief_preview": brief[:1200]}


def _write_legacy_prd(cwd_path: Path, session_id: str, brief_path: Path, *, max_iterations: int, write_json_fn) -> Path:
    prd_path = cwd_path / ".omx" / "prd.json"
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_fn(
        prd_path,
        {
            "project": "PaperOrchestra Ralph QA Loop",
            "branchName": f"ralph/paperorchestra-{session_id}",
            "description": (
                "Run the generated PaperOrchestra Ralph brief one bounded qa-loop-step at a time. "
                "Stop on human_needed, ready_for_human_finalization, failed, or execution_error."
            ),
            "userStories": [
                {
                    "id": "US-001",
                    "title": "Execute bounded PaperOrchestra QA loop",
                    "description": "As a Ralph operator, run the generated brief and inspect each qa-loop execution artifact before continuing.",
                    "acceptanceCriteria": [
                        f"Use brief: {brief_path}",
                        f"Use max_iterations={max_iterations}",
                        "Do not create an internal PaperOrchestra scheduler",
                        "Record the semantic qa-loop-step exit code",
                    ],
                    "priority": 1,
                    "passes": False,
                }
            ],
        },
    )
    return prd_path


def _write_plan_docs(cwd_path: Path, session_id: str, *, brief_path: Path, step_cmd: str) -> tuple[Path, Path]:
    canonical_prd_path = cwd_path / ".omx" / "plans" / f"prd-paperorchestra-qa-loop-{session_id}.md"
    canonical_test_spec_path = cwd_path / ".omx" / "plans" / f"test-spec-paperorchestra-qa-loop-{session_id}.md"
    canonical_prd_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_prd_path.write_text(_canonical_prd_text(brief_path=brief_path, step_cmd=step_cmd), encoding="utf-8")
    canonical_test_spec_path.write_text(_canonical_test_spec_text(brief_path), encoding="utf-8")
    return canonical_prd_path, canonical_test_spec_path


def _canonical_prd_text(*, brief_path: Path, step_cmd: str) -> str:
    return (
        "\n".join(
            [
                "# PRD — PaperOrchestra OMX Ralph QA Loop Handoff",
                "",
                "## Goal",
                "Use OMX Ralph as the persistent operator for PaperOrchestra quality-loop execution.",
                "",
                "## Non-goal",
                "Do not implement a separate PaperOrchestra scheduler or script loop as the source of truth.",
                "",
                "## Operator contract",
                "- Ralph runs exactly one `paperorchestra qa-loop-step` per turn.",
                "- Exit code `10` means continue via OMX stop-hook/tmux injection.",
                "- Exit codes `0`, `20`, `30`, and `40` are terminal for the operator.",
                f"- Hook marker: `{OMX_TMUX_INJECT_MARKER}`.",
                f"- Hook continuation prompt: `{OMX_TMUX_INJECT_PROMPT}`.",
                "",
                "## Command",
                "```bash",
                step_cmd,
                "```",
                "",
                "## Brief",
                f"`{brief_path}`",
            ]
        )
        + "\n"
    )


def _canonical_test_spec_text(brief_path: Path) -> str:
    return (
        "\n".join(
            [
                "# Test Spec — PaperOrchestra OMX Ralph QA Loop Handoff",
                "",
                "## Acceptance criteria",
                "- `ralph-start --dry-run` emits a handoff manifest and does not launch.",
                "- The handoff manifest records hook marker, continuation prompt, step command, exit-code contract, and evidence paths.",
                "- `ralph-start --launch` invokes `omx ralph --prd <brief>` exactly once.",
                "- Ralph brief instructs the operator to use OMX stop-hook/tmux injection, not a nested PaperOrchestra loop.",
                "- Ralph brief tells the operator to execute supported automatic/semi-automatic actions before stopping on unrelated human-needed actions.",
                "",
                "## Manual smoke",
                "```bash",
                f"script -q -f transcript/ralph-operator.typescript -c 'omx ralph --prd \"$(cat {brief_path})\"'",
                "```",
            ]
        )
        + "\n"
    )


def _handoff_payload(
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
        "hook_contract": _hook_contract(),
        "execution_contract": _execution_contract(
            step_cmd=step_cmd,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
        ),
        "evidence_contract": _evidence_contract(evidence_root_path),
    }


def _hook_contract() -> dict[str, Any]:
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


def _execution_contract(
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


def _evidence_contract(evidence_root_path: Path) -> dict[str, Any]:
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


def launch_omx_ralph(argv: list[str], *, cwd: str | Path | None) -> subprocess.Popen:
    return subprocess.Popen(argv, cwd=Path(cwd or ".").resolve(), start_new_session=True)
