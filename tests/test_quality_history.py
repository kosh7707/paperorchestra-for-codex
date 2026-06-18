from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.session import runtime_root
from paperorchestra.loop_engine.quality.history import _build_cross_iteration, _failing_codes_from_quality_eval
from paperorchestra.loop_engine.quality.policy import HISTORY_FILENAME


def _append_history(root: Path, *entries: dict) -> None:
    path = runtime_root(root) / HISTORY_FILENAME
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def test_cross_iteration_detects_repeated_actionable_failure_and_axis_drop(tmp_path: Path) -> None:
    failure = {"category": "compile", "code": "compile_not_clean", "reason": "latex error"}
    _append_history(
        tmp_path,
        {
            "event_type": "qa_loop_step",
            "session_id": "s1",
            "failing_codes": ["compile_not_clean"],
            "manuscript_hash": "sha256:before",
            "tier_3_axis_scores": {"clarity": 4.5},
            "actionable_failure": failure,
        },
        {
            "event_type": "qa_loop_step",
            "session_id": "s1",
            "failing_codes": ["compile_not_clean"],
            "manuscript_hash": "sha256:middle",
            "tier_3_axis_scores": {"clarity": 4.0},
            "actionable_failure": failure,
        },
    )

    result = _build_cross_iteration(
        tmp_path,
        "s1",
        "sha256:after",
        ["compile_not_clean"],
        5,
        current_axis_scores={"clarity": 3.5},
        current_attempt_consumes_budget=True,
    )

    assert result["budget"]["attempts_used"] == 3
    assert result["regression"]["tier_3_axis_drops"][0]["axis"] == "clarity"
    assert result["regression"]["repeated_actionable_failure"]["detected"] is True
    assert result["regression"]["repeated_actionable_failure"]["count"] == 2


def test_failing_codes_from_quality_eval_dedupes_non_reviewable_and_tiers() -> None:
    result = _failing_codes_from_quality_eval(
        {
            "non_reviewable": {"failing_codes": ["compile_not_clean"]},
            "tiers": {
                "tier_1": {"status": "fail", "failing_codes": ["compile_not_clean", "citation_missing"]},
                "tier_2": {"status": "pass", "failing_codes": ["ignored"]},
            },
        }
    )

    assert result == ["citation_missing", "compile_not_clean"]
