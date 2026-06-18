from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.ralph.state import OMX_TMUX_INJECT_MARKER, OMX_TMUX_INJECT_PROMPT


def write_legacy_prd(cwd_path: Path, session_id: str, brief_path: Path, *, max_iterations: int, write_json_fn) -> Path:
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


def write_plan_docs(cwd_path: Path, session_id: str, *, brief_path: Path, step_cmd: str) -> tuple[Path, Path]:
    canonical_prd_path = cwd_path / ".omx" / "plans" / f"prd-paperorchestra-qa-loop-{session_id}.md"
    canonical_test_spec_path = cwd_path / ".omx" / "plans" / f"test-spec-paperorchestra-qa-loop-{session_id}.md"
    canonical_prd_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_prd_path.write_text(canonical_prd_text(brief_path=brief_path, step_cmd=step_cmd), encoding="utf-8")
    canonical_test_spec_path.write_text(canonical_test_spec_text(brief_path), encoding="utf-8")
    return canonical_prd_path, canonical_test_spec_path


def canonical_prd_text(*, brief_path: Path, step_cmd: str) -> str:
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


def canonical_test_spec_text(brief_path: Path) -> str:
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
