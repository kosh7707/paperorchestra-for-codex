from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState
from paperorchestra.core.session import artifact_path, save_session, set_current_session
from paperorchestra.loop_engine.ralph import handoff
from paperorchestra.loop_engine.ralph.state import OMX_TMUX_INJECT_MARKER, OMX_TMUX_INJECT_PROMPT


def _save_session(tmp_path: Path) -> Path:
    artifact_dir = tmp_path / ".paper-orchestra" / "runs" / "session-1" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paper = artifact_dir / "paper.full.tex"
    paper.write_text("Paper body", encoding="utf-8")
    state = SessionState(
        session_id="session-1",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        current_phase="qa",
        active_artifact="paper.full.tex",
        inputs=InputBundle(
            idea_path="idea.md",
            experimental_log_path="exp.md",
            template_path="template.tex",
            guidelines_path="guide.md",
        ),
        artifacts=ArtifactIndex(paper_full_tex=str(paper)),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)
    return paper


def _write_quality_inputs(tmp_path: Path) -> tuple[Path, Path]:
    quality_eval_path = artifact_path(tmp_path, "quality-eval.fixture.json")
    quality_eval_path.write_text(
        json.dumps(
            {
                "tiers": {
                    "tier_1": {"status": "pass", "failing_codes": []},
                    "tier_2_claim_safety": {
                        "status": "fail",
                        "failing_codes": ["citation_support_unsupported", "section_quality_low"],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    plan_path = artifact_path(tmp_path, "qa-loop.plan.fixture.json")
    plan_path.write_text(
        json.dumps(
            {
                "verdict": "continue",
                "repair_actions": [
                    {
                        "code": "compile_not_clean",
                        "automation": "automatic",
                        "reason": "repair compile report",
                    },
                    {
                        "code": "section_review_missing",
                        "automation": "semi_auto",
                        "reason": "run section critic",
                    },
                    {
                        "code": "citation_support_unsupported",
                        "automation": "automatic",
                        "reason": "unsupported citation action",
                    },
                    {
                        "code": "manual_bibliography_check",
                        "automation": "human_needed",
                        "reason": "needs bibliography owner",
                    },
                    {
                        "code": "unsupported_action",
                        "automation": "automatic",
                        "reason": "not a supported handler",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return quality_eval_path, plan_path


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_build_qa_loop_brief_renders_contract_and_action_buckets(tmp_path: Path) -> None:
    paper = _save_session(tmp_path)
    quality_eval_path, plan_path = _write_quality_inputs(tmp_path)

    brief = handoff.build_qa_loop_brief(
        tmp_path,
        quality_mode="claim_safe",
        max_iterations=3,
        require_live_verification=True,
        accept_mixed_provenance=True,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
    )

    assert "# PaperOrchestra Ralph Brief" in brief
    assert "Session: `session-1`" in brief
    assert "Current plan verdict: `continue`" in brief
    assert "Failing codes: `citation_support_unsupported, section_quality_low`" in brief
    assert f"Quality eval: `{quality_eval_path}`" in brief
    assert f"QA loop plan: `{plan_path}`" in brief
    assert f"Current manuscript: `{paper}`" in brief
    assert "--max-iterations 3" in brief
    assert "--require-live-verification" in brief
    assert "--accept-mixed-provenance" in brief
    assert "PAPERO_MODEL_CMD is required for claim-safe Ralph handoff" in brief
    assert "PAPERO_WEB_PROVIDER_CMD is required for claim-safe citation support" in brief
    executable = _section(brief, "## Executable repair actions", "## Human-needed / non-executable actions")
    human_needed = _section(brief, "## Human-needed / non-executable actions", "## All repair actions")
    all_actions = _section(brief, "## All repair actions", "## Evidence to inspect after every step")
    assert "- `compile_not_clean` (automatic): repair compile report" in executable
    assert "- `section_review_missing` (semi_auto): run section critic" in executable
    assert "citation_support_unsupported" not in executable
    assert "unsupported_action" not in executable
    assert "- `manual_bibliography_check`: needs bibliography owner" in human_needed
    assert "- `citation_support_unsupported` (automatic): unsupported citation action" in all_actions
    assert "- `unsupported_action` (automatic): not a supported handler" in all_actions
    assert f"- marker: `{OMX_TMUX_INJECT_MARKER}`" in brief
    assert f"- continuation prompt: `{OMX_TMUX_INJECT_PROMPT}`" in brief


def test_write_qa_loop_brief_uses_default_artifact_name(tmp_path: Path) -> None:
    _save_session(tmp_path)
    quality_eval_path, plan_path = _write_quality_inputs(tmp_path)

    path, text = handoff.write_qa_loop_brief(
        tmp_path,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
    )

    assert path == artifact_path(tmp_path, "ralph-brief.md")
    assert path.read_text(encoding="utf-8") == text


def test_build_ralph_start_payload_writes_manifest_and_uses_brief_text_argv(monkeypatch, tmp_path: Path) -> None:
    _save_session(tmp_path)
    brief_path = artifact_path(tmp_path, "ralph-brief.md")
    brief_text = "# Brief\nRun one step.\n"

    def write_brief(cwd, output_path=None, **kwargs):
        path = Path(output_path).resolve() if output_path else brief_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(brief_text, encoding="utf-8")
        return path, brief_text

    monkeypatch.setattr(handoff, "write_qa_loop_brief", write_brief)
    monkeypatch.setattr(handoff, "_qa_loop_step_command", lambda **kwargs: "facade-step-command --flag")

    payload = handoff.build_ralph_start_payload(
        tmp_path,
        quality_mode="claim_safe",
        max_iterations=5,
        require_live_verification=True,
        accept_mixed_provenance=True,
        evidence_root=tmp_path / "evidence",
    )

    written_payload = json.loads(Path(payload["handoff_path"]).read_text(encoding="utf-8"))
    assert {k: v for k, v in payload.items() if k != "brief_preview"} == written_payload
    assert payload["brief_preview"] == brief_text[:1200]
    assert Path(payload["brief_path"]).exists()
    assert Path(payload["handoff_path"]).exists()
    assert Path(payload["prd_path"]).exists()
    assert Path(payload["canonical_prd_path"]).exists()
    assert Path(payload["canonical_test_spec_path"]).exists()
    assert payload["argv"] == ["omx", "ralph", "--prd", brief_text]
    step_command = payload["execution_contract"]["step_command"]
    canonical_prd = Path(payload["canonical_prd_path"]).read_text(encoding="utf-8")
    assert step_command == "facade-step-command --flag"
    assert step_command in canonical_prd
    assert payload["hook_contract"]["marker"] == OMX_TMUX_INJECT_MARKER
    assert payload["hook_contract"]["continuation_prompt"] == OMX_TMUX_INJECT_PROMPT
    assert payload["execution_contract"]["ralph_required"] is True
    assert payload["execution_contract"]["critic_required"] is True
    assert payload["execution_contract"]["citation_integrity_gate_required"] is True
    assert payload["evidence_contract"]["evidence_root"] == str((tmp_path / "evidence").resolve())
