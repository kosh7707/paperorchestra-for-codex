from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, runtime_root, save_session
from paperorchestra.feedback import human_needed_apply
from paperorchestra.feedback import human_needed
from paperorchestra.feedback.operator_contract import build_operator_review_packet
from paperorchestra.feedback.packet_artifacts import _file_sha256


def _session_with_human_needed_packet(tmp_path: Path) -> tuple[Path, Path, Any]:
    for name, content in {
        "idea.md": "idea",
        "experimental_log.md": "experiment",
        "template.tex": "template",
        "guidelines.md": "guidelines",
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental_log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
    )
    paper_path = artifact_path(tmp_path, "paper.full.tex")
    paper_path.write_text("\\section{Intro}\nA paper.\n", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper_path)
    save_session(tmp_path, state)

    write_json(
        artifact_path(tmp_path, "qa-loop.plan.json"),
        {
            "verdict": "human_needed",
            "session_id": state.session_id,
            "quality_eval_summary": {"manuscript_hash": _file_sha256(paper_path)},
            "repair_actions": [
                {
                    "id": "manual-citation",
                    "automation": "human_needed",
                    "code": "citation_missing",
                    "target": "Related Work",
                    "reason": "Citation judgment needed.",
                    "suggested_action": "Decide how the citation should be repaired.",
                }
            ],
        },
    )
    packet_path, _packet = build_operator_review_packet(tmp_path, review_scope="tex_only")
    return tmp_path, packet_path, state


def test_record_human_needed_answer_writes_redacted_public_artifacts(tmp_path: Path) -> None:
    cwd, packet_path, _state = _session_with_human_needed_packet(tmp_path)

    result = human_needed.record_human_needed_answer(
        cwd,
        "Please repair the citation grounding.",
        packet_path=packet_path,
        redacted_answer_only=True,
    )

    assert result["execution"] == "human_needed_answer_recorded"
    assert result["answer"] == "redacted"
    assert result["decision_kind"] == "generate_new_operator_candidate"
    assert result["handoff_type"] == "citation_author_judgment"
    assert result["target_action_id"] == "manual-citation"
    assert result["private_answer_artifact_sha256"] is None
    assert result["target_issue_ids"]

    feedback = read_json(result["feedback_path"])
    assert feedback["intent"] == "generate_new_operator_candidate"
    assert feedback["issues"][0]["source_item_key"] == "citation_missing"
    assert feedback["human_needed_answer"]["answer"] == "redacted"
    assert "Please repair" not in Path(result["public_answer_artifact"]).read_text(encoding="utf-8")


def test_record_human_needed_answer_writes_private_answer_outside_public_artifacts(tmp_path: Path) -> None:
    cwd, packet_path, state = _session_with_human_needed_packet(tmp_path)

    result = human_needed.record_human_needed_answer(cwd, "Reject this unsafe direction.", packet_path=packet_path)

    assert result["decision_kind"] == "reject_candidate_with_reason"
    assert result["private_answer_artifact_sha256"]
    private_dir = runtime_root(cwd) / "private" / "human-needed" / state.session_id
    private_answers = list(private_dir.glob("answer-*.json"))
    assert len(private_answers) == 1
    private_payload = read_json(private_answers[0])
    assert private_payload["answer"] == "Reject this unsafe direction."
    assert result["answer"] == "redacted"
    assert "Reject this unsafe" not in Path(result["feedback_path"]).read_text(encoding="utf-8")


def test_record_human_needed_answer_rejects_private_output_in_project_root(tmp_path: Path) -> None:
    cwd, packet_path, _state = _session_with_human_needed_packet(tmp_path)

    with pytest.raises(ContractError, match="private answer output"):
        human_needed.record_human_needed_answer(
            cwd,
            "Please proceed with a bounded repair.",
            packet_path=packet_path,
            output_answer=tmp_path / "answer.json",
        )


def test_record_human_needed_answer_apply_path_attaches_execution_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cwd, packet_path, _state = _session_with_human_needed_packet(tmp_path)
    imported_path = artifact_path(cwd, "imported-feedback.json")
    execution_path = artifact_path(cwd, "operator-feedback.execution.json")
    write_json(imported_path, {"ok": True})
    write_json(
        execution_path,
        {
            "verdict": "human_needed",
            "promotion_status": "not_promoted",
            "promotion_reason": "needs author",
            "supervised_iteration_index": 0,
            "supervised_remaining": 1,
            "candidate_branch": "candidate/one",
        },
    )
    calls: dict[str, Any] = {}

    def fake_import_operator_feedback(cwd_arg: Path, **kwargs: Any) -> tuple[Path, dict[str, Any]]:
        calls["import"] = {"cwd": cwd_arg, **kwargs}
        return imported_path, read_json(imported_path)

    def fake_apply_operator_feedback(cwd_arg: Path, provider: Any, **kwargs: Any) -> tuple[Path, dict[str, Any]]:
        calls["apply"] = {"cwd": cwd_arg, "provider": provider, **kwargs}
        return execution_path, read_json(execution_path)

    monkeypatch.setattr(human_needed_apply, "import_operator_feedback", fake_import_operator_feedback)
    monkeypatch.setattr(human_needed_apply, "apply_operator_feedback", fake_apply_operator_feedback)

    result = human_needed.record_human_needed_answer(
        cwd,
        "Please run the bounded repair.",
        packet_path=packet_path,
        redacted_answer_only=True,
        apply=True,
        max_supervised_iterations=2,
        require_compile=True,
    )

    assert calls["import"]["packet_path"] == packet_path
    assert calls["import"]["feedback_path"] == Path(result["feedback_path"])
    assert calls["apply"]["imported_feedback_path"] == imported_path
    assert calls["apply"]["max_supervised_iterations"] == 2
    assert calls["apply"]["require_compile"] is True
    assert result["operator_feedback_execution_summary"] == {
        "verdict": "human_needed",
        "promotion_status": "not_promoted",
        "promotion_reason": "needs author",
        "supervised_iteration_index": 0,
        "supervised_remaining": 1,
        "candidate_branch": "candidate/one",
    }
