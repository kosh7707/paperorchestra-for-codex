from __future__ import annotations

from paperorchestra.core.models import SessionState


def test_session_state_ignores_unknown_runtime_fields() -> None:
    payload = {
        "session_id": "po-schema",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "current_phase": "draft_available",
        "active_artifact": "paper.full.pdf",
        "inputs": {
            "idea_path": "idea.md",
            "experimental_log_path": "experiment.md",
            "template_path": "template.tex",
            "guidelines_path": "guidelines.md",
            "future_input_field": "ignored",
        },
        "artifacts": {
            "paper_full_tex": "paper.full.tex",
            "compiled_pdf": "paper.full.pdf",
            "latest_page_layout_review_json": "page-layout-review.json",
            "future_artifact_field": "ignored",
        },
        "review_history": [
            {
                "overall_score": 0.9,
                "raw_path": "review.json",
                "future_score_field": "ignored",
            }
        ],
        "future_session_field": "ignored",
    }

    state = SessionState.from_dict(payload)

    assert state.inputs.idea_path == "idea.md"
    assert state.artifacts.latest_page_layout_review_json == "page-layout-review.json"
    assert state.review_history[0].overall_score == 0.9
    assert not hasattr(state.artifacts, "future_artifact_field")
