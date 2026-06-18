from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.handoff_brief_context import RalphBriefContext
from paperorchestra.loop_engine.ralph.state import OMX_TMUX_INJECT_MARKER, OMX_TMUX_INJECT_PROMPT


def render_qa_loop_brief(context: RalphBriefContext) -> str:
    lines = _header_lines(context, context.plan)
    _append_action_section(lines, "## Executable repair actions", context.action_buckets.executable_actions)
    _append_action_section(lines, "## Human-needed / non-executable actions", context.action_buckets.human_actions, human=True)
    _append_action_section(lines, "## All repair actions", context.action_buckets.actions)
    lines.extend(_evidence_and_handoff_lines())
    return "\n".join(lines) + "\n"


def _header_lines(context: RalphBriefContext, plan: dict[str, Any]) -> list[str]:
    state = context.state
    return [
        "# PaperOrchestra Ralph Brief",
        "",
        f"Session: `{state.session_id}`",
        f"Quality mode: `{context.quality_mode}`",
        "",
        "## Verdict alphabet",
        "",
        "The only valid loop states are `continue`, `human_needed`, `ready_for_human_finalization`, and `failed`.",
        "There is no terminal state named `success`; Tier 4 always remains human-owned.",
        "",
        "## Current status",
        "",
        f"Current plan verdict: `{plan.get('verdict')}`",
        f"Failing codes: `{', '.join(context.failing_codes) if context.failing_codes else 'none'}`",
        f"Quality eval: `{context.quality_eval_path}`",
        f"QA loop plan: `{context.plan_path}`",
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
        context.step_command,
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
    ]


def _append_action_section(lines: list[str], title: str, actions: list[dict[str, Any]], *, human: bool = False) -> None:
    lines.extend([title, ""])
    if actions:
        for action in actions:
            if human:
                lines.append(f"- `{action.get('code')}`: {action.get('reason')}")
            else:
                lines.append(f"- `{action.get('code')}` ({action.get('automation')}): {action.get('reason')}")
    else:
        lines.append("- none")
    lines.append("")


def _evidence_and_handoff_lines() -> list[str]:
    return [
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
