from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.ralph import repair


class DummyProvider:
    pass


def _state(paper_path: Path, citation_map_path: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        artifacts=SimpleNamespace(
            paper_full_tex=str(paper_path),
            citation_map_json=str(citation_map_path) if citation_map_path else None,
        ),
        notes=[],
    )


def test_repair_citation_claims_returns_accepted_when_no_issues(tmp_path: Path, monkeypatch) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("original", encoding="utf-8")

    monkeypatch.setattr(repair, "recover_pending_manuscript_write", lambda cwd: None)
    monkeypatch.setattr(repair, "load_session", lambda cwd: _state(paper))
    monkeypatch.setattr(repair, "_session_mutation_snapshot", lambda state: {"snapshot": True})
    monkeypatch.setattr(repair, "_read_json", lambda path: {})
    monkeypatch.setattr(repair, "_non_supported_citation_items", lambda review: [])
    monkeypatch.setattr(repair, "_claim_safety_repair_issues", lambda cwd: [])
    monkeypatch.setattr(repair, "utc_now_iso", lambda: "now")

    result = repair.repair_citation_claims(tmp_path, DummyProvider())

    assert result["accepted"] is True
    assert result["reason"] == "no_citation_claim_or_claim_safety_issues"
    assert result["completed_at"] == "now"


def test_repair_citation_claims_restores_original_on_validation_failure(tmp_path: Path, monkeypatch) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("original", encoding="utf-8")
    citation_map = tmp_path / "citation_map.json"
    citation_map.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(repair, "recover_pending_manuscript_write", lambda cwd: calls.append("recover"))
    monkeypatch.setattr(repair, "load_session", lambda cwd: _state(paper, citation_map))
    monkeypatch.setattr(repair, "_session_mutation_snapshot", lambda state: {"snapshot": True})
    monkeypatch.setattr(repair, "_read_json", lambda path: {"key1": "Paper"} if Path(path) == citation_map else {"review": True})
    monkeypatch.setattr(repair, "_non_supported_citation_items", lambda review: [{"id": "issue"}])
    monkeypatch.setattr(repair, "_claim_safety_repair_issues", lambda cwd: [])
    monkeypatch.setattr(repair, "_source_obligation_repair_context", lambda cwd: {})
    monkeypatch.setattr(repair, "_repair_prompt", lambda *args: ("system", "user"))
    monkeypatch.setattr(repair, "_build_completion_request", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        repair,
        "_complete_with_runtime_mode",
        lambda *args, **kwargs: ("candidate response", "compatibility", False, []),
    )
    monkeypatch.setattr(repair, "extract_latex", lambda response: "candidate with \\cite{key1}")
    monkeypatch.setattr(repair, "canonical_citation_map", lambda citation_map: citation_map)
    monkeypatch.setattr(repair, "canonicalize_citation_keys", lambda candidate, citation_map: (candidate, []))
    monkeypatch.setattr(repair, "allowed_citation_keys", lambda citation_map: {"key1"})
    monkeypatch.setattr(repair, "extract_citation_keys", lambda candidate: {"key1"})
    monkeypatch.setattr(repair, "artifact_path", lambda cwd, name: tmp_path / name)
    monkeypatch.setattr(
        repair,
        "guarded_replace_manuscript_text",
        lambda cwd, path, text, reason, original_text: calls.append(f"guard:{reason}:{original_text}:{text}"),
    )
    monkeypatch.setattr(
        repair,
        "record_current_validation_report",
        lambda cwd, name: (tmp_path / name, {"ok": False, "blocking_issue_count": 2}),
    )
    monkeypatch.setattr(
        repair,
        "atomic_write_text",
        lambda path, text: calls.append(f"restore-file:{text}") or Path(path).write_text(text, encoding="utf-8"),
    )
    monkeypatch.setattr(
        repair,
        "clear_pending_manuscript_write",
        lambda cwd, status, reason: calls.append(f"clear:{status}:{reason}"),
    )
    monkeypatch.setattr(
        repair,
        "_restore_session_mutation_snapshot",
        lambda cwd, snapshot: calls.append(f"restore-session:{snapshot['snapshot']}"),
    )
    monkeypatch.setattr(
        repair,
        "_candidate_semantic_recheck",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("semantic recheck should not run")),
    )
    monkeypatch.setattr(repair, "utc_now_iso", lambda: "now")

    result = repair.repair_citation_claims(tmp_path, DummyProvider())

    assert result["accepted"] is False
    assert result["reason"] == "validation_failed"
    assert result["validation"] == {"path": str(tmp_path / "validation.citation-repair.json"), "ok": False, "blocking_issue_count": 2}
    assert paper.read_text(encoding="utf-8") == "original"
    assert calls == [
        "recover",
        "guard:citation_repair_candidate_validation:original:candidate with \\cite{key1}",
        "restore-file:original",
        "clear:restored:citation_repair_validation_failed",
        "restore-session:True",
    ]


def test_repair_citation_claims_stops_before_mutation_on_unknown_citations(tmp_path: Path, monkeypatch) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("original", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(repair, "recover_pending_manuscript_write", lambda cwd: None)
    monkeypatch.setattr(repair, "load_session", lambda cwd: _state(paper))
    monkeypatch.setattr(repair, "_session_mutation_snapshot", lambda state: {"snapshot": True})
    monkeypatch.setattr(repair, "_read_json", lambda path: {"review": True})
    monkeypatch.setattr(repair, "_non_supported_citation_items", lambda review: [{"id": "issue"}])
    monkeypatch.setattr(repair, "_claim_safety_repair_issues", lambda cwd: [])
    monkeypatch.setattr(repair, "_source_obligation_repair_context", lambda cwd: {})
    monkeypatch.setattr(repair, "_repair_prompt", lambda *args: ("system", "user"))
    monkeypatch.setattr(repair, "_build_completion_request", lambda **kwargs: kwargs)
    monkeypatch.setattr(repair, "_complete_with_runtime_mode", lambda *args, **kwargs: ("candidate", "compatibility", False, []))
    monkeypatch.setattr(repair, "extract_latex", lambda response: "candidate with \\cite{unknown}")
    monkeypatch.setattr(repair, "canonical_citation_map", lambda citation_map: citation_map)
    monkeypatch.setattr(repair, "canonicalize_citation_keys", lambda candidate, citation_map: (candidate, []))
    monkeypatch.setattr(repair, "allowed_citation_keys", lambda citation_map: set())
    monkeypatch.setattr(repair, "extract_citation_keys", lambda candidate: {"unknown"})
    monkeypatch.setattr(repair, "artifact_path", lambda cwd, name: tmp_path / name)
    monkeypatch.setattr(repair, "guarded_replace_manuscript_text", lambda *args, **kwargs: calls.append("guard"))
    monkeypatch.setattr(repair, "utc_now_iso", lambda: "now")

    result = repair.repair_citation_claims(tmp_path, DummyProvider())

    assert result["reason"] == "unknown_citation_keys"
    assert result["unknown_citation_keys"] == ["unknown"]
    assert calls == []
