from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.reviews.evaluation_io import _write_json_artifact
from paperorchestra.reviews.review_gate_payload import build_review_gate_payload


def build_review_gate_comparison(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    latest_review = read_json(state.artifacts.latest_review_json) if state.artifacts.latest_review_json and Path(state.artifacts.latest_review_json).exists() else {}
    return build_review_gate_payload(
        session_id=state.session_id,
        review_path=state.artifacts.latest_review_json,
        latest_review=latest_review,
    )


def write_review_gate_comparison(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_review_gate_comparison(cwd)
    return _write_json_artifact(payload, output_path)
