from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.ralph import bridge_rollback as rollback_module


def test_restore_candidate_after_exception_restores_original_and_session(monkeypatch, tmp_path: Path) -> None:
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("candidate", encoding="utf-8")
    cleared: list[dict] = []
    restored: list[dict] = []
    rollback = rollback_module.QaLoopRollbackContext(
        paper_path=paper_path,
        original_paper="original",
        mutation_snapshot={"state": "before"},
        citation_review_snapshot={"path": None, "exists": False, "content": None},
        citation_trace_snapshot={"path": None, "exists": False, "content": None},
    )

    monkeypatch.setattr(rollback_module, "clear_pending_manuscript_write", lambda cwd, **kwargs: cleared.append({"cwd": cwd, **kwargs}))
    monkeypatch.setattr(rollback_module, "_restore_session_mutation_snapshot", lambda cwd, snapshot: restored.append({"cwd": cwd, "snapshot": snapshot}))

    rollback_module.restore_candidate_after_exception(
        cwd=tmp_path,
        rollback=rollback,
        citation_candidate_applied=True,
    )

    assert paper_path.read_text(encoding="utf-8") == "original"
    assert cleared == [{"cwd": tmp_path, "status": "restored", "reason": "qa_loop_candidate_exception"}]
    assert restored == [{"cwd": tmp_path, "snapshot": {"state": "before"}}]
