from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from .io_utils import write_json
from .quality_loop import DEFAULT_MAX_ITERATIONS, write_quality_eval, write_quality_loop_plan
from .ralph_bridge_state import (
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    _failing_codes,
    _qa_loop_step_command,
    _read_json,
)
from .session import artifact_path, load_session


def build_qa_loop_brief(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    quality_eval_path: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> str:
    state = load_session(cwd)
    if quality_eval_path and Path(quality_eval_path).exists():
        quality_eval = _read_json(quality_eval_path)
    else:
        _, quality_eval = write_quality_eval(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
        )
        quality_eval_path = artifact_path(cwd, "quality-eval.json")
    if plan_path and Path(plan_path).exists():
        plan = _read_json(plan_path)
    else:
        plan_path, plan = write_quality_loop_plan(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            quality_eval_input_path=quality_eval_path,
        )
    failing_codes = _failing_codes(quality_eval if isinstance(quality_eval, dict) else {})
    actions = plan.get("repair_actions", []) if isinstance(plan, dict) else []
    executable_actions = [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) in SUPPORTED_HANDLER_CODES
    ]
    human_actions = [action for action in actions if isinstance(action, dict) and action.get("automation") == "human_needed"]
    step_cmd = _qa_loop_step_command(
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    lines = [
        "# PaperOrchestra Ralph Brief",
        "",
        f"Session: `{state.session_id}`",
        f"Quality mode: `{quality_mode}`",
        "",
        "## Verdict alphabet",
        "",
        "The only valid loop states are `continue`, `human_needed`, `ready_for_human_finalization`, and `failed`.",
        "There is no terminal state named `success`; Tier 4 always remains human-owned.",
        "",
        "## Current status",
        "",
        f"Current plan verdict: `{plan.get('verdict') if isinstance(plan, dict) else 'unknown'}`",
        f"Failing codes: `{', '.join(failing_codes) if failing_codes else 'none'}`",
        f"Quality eval: `{quality_eval_path}`",
        f"QA loop plan: `{plan_path}`",
        f"Current manuscript: `{state.artifacts.paper_full_tex}`",
        "",
        "## Ralph execution rule",
        "",
        "You are the OMX Ralph operator. Do not emulate Ralph inside PaperOrchestra.",
        "Claim-safe contract: Ralph continuation is required; direct manual continuation without this handoff is non-conformant.",
        "Claim-safe contract: Citation Integrity and Critic artifacts are required before readiness can be claimed.",
        "Run exactly one PaperOrchestra repair step at a time, then re-read the resulting `qa-loop-execution.iter-*.json` artifact.",
        "OMX stop-hook/tmux injection owns persistence and continuation. The expected injection marker is `[OMX_TMUX_INJECT]` and the injected prompt is `Continue from current mode state. [OMX_TMUX_INJECT]`.",
        "Before running the step, ensure `PAPERO_MODEL_CMD` is the generation provider command and `PAPERO_WEB_PROVIDER_CMD` is the trace-wrapped web citation provider command.",
        "If either variable is missing, stop with `human_needed`; do not silently switch to a mock or non-web provider.",
        "",
        "```bash",
        'test -n "${PAPERO_MODEL_CMD:-}" || { echo "PAPERO_MODEL_CMD is required for claim-safe Ralph handoff"; exit 20; }',
        'test -n "${PAPERO_WEB_PROVIDER_CMD:-}" || { echo "PAPERO_WEB_PROVIDER_CMD is required for claim-safe citation support"; exit 20; }',
        "```",
        "",
        "```bash",
        step_cmd,
        "```",
        "",
        "## Stop rules",
        "",
        "- Stop and report when `qa-loop-step` returns `human_needed`, `failed`, or `ready_for_human_finalization`.",
        "- Continue only when it returns `continue` and the execution artifact shows forward progress.",
        "- If the plan verdict is `continue`, execute the first supported automatic/semi-automatic action via `qa-loop-step`; do not stop only because separate human-needed actions are also listed.",
        "- If `qa-loop-step` reports `no_progress_override=true`, stop and report `human_needed`.",
        "- If the same failing-code set repeats or citation issue count rises after a repair, stop and report rather than softening claims dishonestly.",
        "- Never automate final figures, proof rigor, bibliography curation, venue fit, or submission decision.",
        "",
        "## Exit code contract",
        "",
        "- `0` — ready_for_human_finalization: stop; Tier 4 remains human-owned.",
        "- `10` — continue: allow OMX hook/tmux injection to continue from current state.",
        "- `20` — human_needed: stop and surface the execution artifact.",
        "- `30` — failed: stop and surface the execution artifact.",
        "- `40` — execution_error: stop and surface the exception plus rollback evidence.",
        "",
        "## Executable repair actions",
        "",
    ]
    if executable_actions:
        for action in executable_actions:
            lines.append(f"- `{action.get('code')}` ({action.get('automation')}): {action.get('reason')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Human-needed / non-executable actions", ""])
    if human_actions:
        for action in human_actions:
            lines.append(f"- `{action.get('code')}`: {action.get('reason')}")
    else:
        lines.append("- none")
    lines.extend(["", "## All repair actions", ""])
    if actions:
        for action in actions:
            lines.append(f"- `{action.get('code')}` ({action.get('automation')}): {action.get('reason')}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Evidence to inspect after every step",
            "",
            "- `.paper-orchestra/qa-loop-execution.iter-*.json` — semantic step result and exit-code meaning.",
            "- `.paper-orchestra/qa-loop-history.jsonl` — budget-consuming iteration history.",
            "- `.paper-orchestra/runs/<session>/artifacts/quality-eval.json` — tiered diagnostic snapshot.",
            "- `.paper-orchestra/runs/<session>/artifacts/qa-loop.plan.json` — current policy/action plan.",
            "- `.paper-orchestra/runs/<session>/artifacts/citation_support_review.json` — claim-support critic details.",
            "- `.paper-orchestra/runs/<session>/artifacts/section_review.json` — section-quality critic details.",
            "",
            "## Raw OMX hook contract",
            "",
            f"- marker: `{OMX_TMUX_INJECT_MARKER}`",
            f"- continuation prompt: `{OMX_TMUX_INJECT_PROMPT}`",
            "- Ralph mode must stay active until a terminal PaperOrchestra verdict is observed.",
            "- Do not create a nested loop outside OMX; rely on hook continuation between single-step executions.",
            "",
            "## Suggested OMX handoff",
            "",
            "```bash",
            "omx ralph --prd \"$(cat .paper-orchestra/runs/<session>/artifacts/ralph-brief.md)\"",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"

def write_qa_loop_brief(cwd: str | Path | None, output_path: str | Path | None = None, **kwargs: Any) -> tuple[Path, str]:
    text = build_qa_loop_brief(cwd, **kwargs)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, QA_LOOP_BRIEF_FILENAME)
    path.write_text(text, encoding="utf-8")
    return path, text

def build_ralph_start_payload(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_path: str | Path | None = None,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    brief_path, brief = write_qa_loop_brief(
        cwd,
        output_path,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    state = load_session(cwd)
    cwd_path = Path(cwd or ".").resolve()
    prd_path = Path(cwd or ".").resolve() / ".omx" / "prd.json"
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_prd_path = cwd_path / ".omx" / "plans" / f"prd-paperorchestra-qa-loop-{state.session_id}.md"
    canonical_test_spec_path = cwd_path / ".omx" / "plans" / f"test-spec-paperorchestra-qa-loop-{state.session_id}.md"
    canonical_prd_path.parent.mkdir(parents=True, exist_ok=True)
    step_cmd = _qa_loop_step_command(
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    write_json(
        prd_path,
        {
            "project": "PaperOrchestra Ralph QA Loop",
            "branchName": f"ralph/paperorchestra-{state.session_id}",
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
    canonical_prd_path.write_text(
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
        + "\n",
        encoding="utf-8",
    )
    canonical_test_spec_path.write_text(
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
        + "\n",
        encoding="utf-8",
    )
    command = ["omx", "ralph", "--prd", brief_path.read_text(encoding="utf-8")]
    handoff_path = artifact_path(cwd, QA_LOOP_HANDOFF_FILENAME)
    evidence_root_path = Path(evidence_root).resolve() if evidence_root else cwd_path
    payload = {
        "schema_version": "paperorchestra-ralph-handoff/1",
        "session_id": state.session_id,
        "brief_path": str(brief_path),
        "prd_path": str(prd_path),
        "canonical_prd_path": str(canonical_prd_path),
        "canonical_test_spec_path": str(canonical_test_spec_path),
        "handoff_path": str(handoff_path),
        "suggested_command": "omx ralph --prd \"$(cat " + str(brief_path) + ")\"",
        "operator_transcript_command": "script -q -f transcript/ralph-operator.typescript -c "
        + shlex.quote("omx ralph --prd \"$(cat " + str(brief_path) + ")\""),
        "argv": command,
        "hook_contract": {
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
        },
        "execution_contract": {
            "step_command": step_cmd,
            "ralph_required": quality_mode == "claim_safe",
            "critic_required": quality_mode == "claim_safe",
            "citation_integrity_gate_required": quality_mode == "claim_safe",
            "human_needed_cycle_policy": {"requested_cycles": max_iterations, "observed_cycles": None, "counter_source": ".paper-orchestra/qa-loop-history.jsonl"},
            "requires_papero_model_cmd": True,
            "requires_papero_web_provider_cmd": True,
            "requires_web_search_provider": True,
            "quality_mode": quality_mode,
            "max_iterations": max_iterations,
            "require_live_verification": require_live_verification,
            "accept_mixed_provenance": accept_mixed_provenance,
        },
        "evidence_contract": {
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
        },
    }
    write_json(handoff_path, payload)
    return {
        **payload,
        "brief_preview": brief[:1200],
    }

def launch_omx_ralph(argv: list[str], *, cwd: str | Path | None) -> subprocess.Popen:
    return subprocess.Popen(argv, cwd=Path(cwd or ".").resolve(), start_new_session=True)
