from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session
from paperorchestra.loop_engine.ralph import action_dispatch_citation_refresh as citation_refresh
from paperorchestra.loop_engine.ralph import action_dispatch_citation_repair as citation_repair
from paperorchestra.loop_engine.ralph import action_dispatch_handlers as handlers
from paperorchestra.loop_engine.ralph.action_dispatch import dispatch_qa_loop_actions
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext
from paperorchestra.loop_engine.quality.policy import QA_LOOP_SUPPORTED_HANDLER_CODES
from paperorchestra.runtime.mock_provider import MockProvider


def _context(tmp_path: Path, *, paper_path: Path | None = None) -> QaLoopActionDispatchContext:
    return QaLoopActionDispatchContext(
        cwd=tmp_path,
        provider=MockProvider(),
        runtime_mode="compatibility",
        require_compile=False,
        quality_mode="claim_safe",
        citation_evidence_mode="offline",
        citation_provider=None,
        paper_path=paper_path,
        original_paper="original paper",
    )


def _execution() -> dict:
    return {"actions_attempted": [], "actions_skipped": []}


def _write(path: Path, text: str = "x") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _seed_runtime_session(tmp_path: Path) -> None:
    create_session(
        tmp_path,
        InputBundle(
            idea_path=str(_write(tmp_path / "idea.md")),
            experimental_log_path=str(_write(tmp_path / "experimental.md")),
            template_path=str(_write(tmp_path / "template.tex", "\\documentclass{article}")),
            guidelines_path=str(_write(tmp_path / "guidelines.md")),
        ),
        allow_outside_workspace=True,
    )


def test_supported_handler_codes_are_covered_by_registry() -> None:
    assert handlers.handled_action_codes() == set(QA_LOOP_SUPPORTED_HANDLER_CODES)


def test_dispatch_routes_refresh_action_families_and_skips_unknown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        handlers,
        "plan_narrative_and_claims",
        lambda cwd, provider, runtime_mode: {"narrative_plan": tmp_path / "narrative.json"},
    )
    monkeypatch.setattr(
        handlers,
        "record_current_validation_report",
        lambda cwd, name: (tmp_path / name, {"ok": True}),
    )
    monkeypatch.setattr(
        citation_refresh,
        "write_citation_support_review",
        lambda cwd, provider, evidence_mode: tmp_path / "citation-review.json",
    )
    monkeypatch.setattr(
        citation_refresh,
        "_refresh_citation_integrity_for_current_manuscript",
        lambda cwd, quality_mode: {"integrity": "refreshed"},
    )
    execution = _execution()

    result = dispatch_qa_loop_actions(
        [
            {"code": "narrative_plan_missing"},
            {"code": "validation_report_missing"},
            {"code": "citation_support_review_missing"},
            {"code": "citation_integrity_missing"},
            {"code": "unknown_future_code"},
        ],
        execution,
        _context(tmp_path),
    )

    assert result.citation_candidate_applied is False
    assert [item["handler"] for item in execution["actions_attempted"]] == [
        "plan_narrative",
        "validate_current",
        "critique_citations",
        "refresh_citation_integrity",
    ]
    assert execution["actions_skipped"] == [{"code": "unknown_future_code", "reason": "no_handler"}]


def test_dispatch_compile_failure_stops_later_actions(tmp_path: Path, monkeypatch) -> None:
    def fail_compile(cwd):
        raise RuntimeError("latex broke")

    def unexpected_review(*args, **kwargs):
        raise AssertionError("review should not run after compile failure")

    monkeypatch.setattr(handlers, "compile_current_paper", fail_compile)
    monkeypatch.setattr(handlers, "review_current_paper", unexpected_review)
    execution = _execution()

    result = dispatch_qa_loop_actions(
        [{"code": "compile_not_clean"}, {"code": "review_score_missing"}],
        execution,
        _context(tmp_path),
    )

    assert result.citation_candidate_applied is False
    assert execution["actions_attempted"] == [
        {"code": "compile_not_clean", "handler": "compile", "ok": False, "error": "latex broke"}
    ]
    assert execution["actions_skipped"] == []


def test_dispatch_records_actionable_failure_when_citation_repair_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        citation_repair,
        "repair_citation_claims",
        lambda *args, **kwargs: {"accepted": False, "reason": "semantic_recheck_failed", "validation": {"ok": False}},
    )
    execution = _execution()

    result = dispatch_qa_loop_actions(
        [{"code": "citation_support_critic_failed"}, {"code": "review_score_missing"}],
        execution,
        _context(tmp_path),
    )

    assert result.citation_candidate_applied is False
    assert execution["actions_attempted"][0]["handler"] == "repair_citation_claims"
    assert execution["actionable_failure"]["category"] == "citation_repair_failed"
    assert execution["actionable_failure"]["validation_failing_codes"] == ["validation_failed"]
    assert len(execution["actions_attempted"]) == 1


def test_dispatch_refine_rejection_stops_later_actions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        handlers,
        "load_session",
        lambda cwd: SimpleNamespace(artifacts=SimpleNamespace(latest_review_json="review.json")),
    )
    monkeypatch.setattr(handlers, "refine_current_paper", lambda *args, **kwargs: [{"accepted": False}])
    monkeypatch.setattr(handlers, "write_section_review", lambda cwd: tmp_path / "section-review.json")
    monkeypatch.setattr(
        handlers,
        "write_source_obligations",
        lambda cwd: (_ for _ in ()).throw(AssertionError("source obligations should not run after refine rejection")),
    )
    execution = _execution()

    result = dispatch_qa_loop_actions(
        [{"code": "review_score_below_threshold"}, {"code": "source_obligations_missing"}],
        execution,
        _context(tmp_path),
    )

    assert result.citation_candidate_applied is False
    assert [item["handler"] for item in execution["actions_attempted"]] == ["refine"]
    assert execution["actions_attempted"][0]["result"] == [{"accepted": False}]


def test_dispatch_preserves_accepted_citation_candidate_for_validation(tmp_path: Path, monkeypatch) -> None:
    _seed_runtime_session(tmp_path)
    paper_path = tmp_path / "paper.tex"
    candidate_path = tmp_path / "candidate.tex"
    paper_path.write_text("original paper", encoding="utf-8")
    candidate_path.write_text("candidate paper", encoding="utf-8")
    replacements = []
    monkeypatch.setattr(
        citation_repair,
        "repair_citation_claims",
        lambda *args, **kwargs: {"accepted": True, "candidate_path": str(candidate_path)},
    )
    monkeypatch.setattr(
        citation_repair,
        "guarded_replace_manuscript_text",
        lambda cwd, path, text, reason, original_text: replacements.append((path, text, reason, original_text)),
    )
    execution = _execution()

    result = dispatch_qa_loop_actions(
        [{"code": "high_risk_uncited_claim"}],
        execution,
        _context(tmp_path, paper_path=paper_path),
    )

    assert result.citation_candidate_applied is True
    attempted_repair = execution["actions_attempted"][0]["result"]
    preserved_path = Path(attempted_repair["candidate_path"])
    assert result.citation_candidate_path == str(preserved_path)
    assert preserved_path.name.startswith("paper.citation-repair.approval-")
    assert preserved_path.read_text(encoding="utf-8") == "candidate paper"
    assert attempted_repair["raw_candidate_path"] == str(candidate_path)
    assert attempted_repair["candidate_sha256"].startswith("sha256:")
    assert replacements == [
        (paper_path, "candidate paper", "qa_loop_citation_candidate_for_validation", "original paper")
    ]
