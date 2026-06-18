from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.feedback.packet_bindings import _execution_payload_sha256
from paperorchestra.feedback.packet_review_openers import (
    _current_bound_execution_path,
    _execution_payload_opens_candidate_review,
    _execution_payload_opens_operator_review,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_candidate_review_opens_only_for_hash_bound_ready_candidate(tmp_path: Path) -> None:
    current_sha = "a" * 64
    candidate = tmp_path / "candidate.tex"
    candidate.write_text("candidate", encoding="utf-8")
    execution_path = tmp_path / "qa-loop.execution.json"
    payload = {
        "verdict": "human_needed",
        "candidate_progress": {"forward_progress": True},
        "candidate_approval": {
            "status": "human_needed_candidate_ready",
            "base_manuscript_sha256": current_sha,
            "created_at": "2026-06-18T00:00:00Z",
            "source_execution_path": str(execution_path),
            "candidate_path": str(candidate),
            "candidate_sha256": "sha256:",
        },
    }
    import hashlib

    payload["candidate_approval"]["candidate_sha256"] += hashlib.sha256(candidate.read_bytes()).hexdigest()
    payload["candidate_approval"]["source_execution_sha256"] = _execution_payload_sha256(payload)
    _write_json(execution_path, payload)

    assert _execution_payload_opens_candidate_review(execution_path, payload, current_manuscript_sha256=current_sha)

    stale = json.loads(json.dumps(payload))
    stale["candidate_progress"]["forward_progress"] = False
    assert not _execution_payload_opens_candidate_review(execution_path, stale, current_manuscript_sha256=current_sha)


def test_operator_review_opens_for_bound_no_progress_or_rejected_handoff(tmp_path: Path) -> None:
    current_sha = "b" * 64
    execution_path = tmp_path / "qa-loop.execution.json"
    no_progress = {
        "verdict": "human_needed",
        "manuscript_sha256_before": current_sha,
        "no_progress_override": True,
    }
    assert _execution_payload_opens_operator_review(execution_path, no_progress, current_manuscript_sha256=current_sha)

    rejected = {
        "verdict": "human_needed",
        "manuscript_sha256_before": current_sha,
        "candidate_handoff": {"status": "human_needed_candidate_rejected_by_operator"},
    }
    assert _execution_payload_opens_operator_review(execution_path, rejected, current_manuscript_sha256=current_sha)

    stale = dict(no_progress, manuscript_sha256_before="c" * 64)
    assert not _execution_payload_opens_operator_review(execution_path, stale, current_manuscript_sha256=current_sha)


def test_current_bound_execution_path_filters_stale_and_unbound_figure_reviews(tmp_path: Path) -> None:
    current_sha = "d" * 64
    current = _write_json(tmp_path / "current.json", {"manuscript_sha256": current_sha})
    stale = _write_json(tmp_path / "stale.json", {"manuscript_sha256": "e" * 64})
    unbound_figure = _write_json(tmp_path / "figure.json", {"status": "pass"})
    unreadable = tmp_path / "bad.json"
    unreadable.write_text("not json", encoding="utf-8")

    assert _current_bound_execution_path(current, role="section_review", current_manuscript_sha256=current_sha) == current
    assert _current_bound_execution_path(stale, role="section_review", current_manuscript_sha256=current_sha) is None
    assert _current_bound_execution_path(unbound_figure, role="figure_placement_review", current_manuscript_sha256=current_sha) is None
    assert _current_bound_execution_path(unreadable, role="section_review", current_manuscript_sha256=current_sha) == unreadable
