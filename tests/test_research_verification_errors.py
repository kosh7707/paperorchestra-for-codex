from __future__ import annotations

from types import SimpleNamespace

from paperorchestra.core.session import set_current_session
from paperorchestra.engine import research_stages, research_verification_errors


def test_record_verification_errors_noops_without_errors(tmp_path) -> None:
    state = SimpleNamespace(artifacts=SimpleNamespace(latest_verification_errors_json=None), notes=[])

    assert (
        research_verification_errors._record_verification_errors(
            tmp_path,
            state,
            [],
            mode="live",
            on_error="skip",
        )
        is None
    )
    assert state.artifacts.latest_verification_errors_json is None
    assert state.notes == []


def test_record_verification_errors_writes_artifact_and_updates_state(tmp_path) -> None:
    set_current_session(tmp_path, "session-1")
    state = SimpleNamespace(artifacts=SimpleNamespace(latest_verification_errors_json=None), notes=[])
    errors = [
        {
            "bucket": "macro_candidates",
            "title_guess": "Missing Paper",
            "error_type": "RuntimeError",
            "message": "boom",
            "action": "skipped",
        }
    ]

    path = research_verification_errors._record_verification_errors(
        tmp_path,
        state,
        errors,
        mode="live",
        on_error="skip",
    )

    assert path is not None
    assert path.name == "verification_errors.json"
    assert state.artifacts.latest_verification_errors_json == str(path)
    assert state.notes == [f"Recorded 1 live verification error(s): {path.name}"]
    payload = path.read_text(encoding="utf-8")
    assert '"mode": "live"' in payload
    assert '"on_error": "skip"' in payload
    assert '"error_count": 1' in payload
    assert "SEMANTIC_SCHOLAR_API_KEY" in payload
