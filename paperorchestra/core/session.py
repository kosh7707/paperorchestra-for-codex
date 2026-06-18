from __future__ import annotations

import uuid
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session_paths import (
    CURRENT_FILE,
    ROOT_DIRNAME,
    artifact_path,
    build_path,
    get_current_session_id,
    project_root,
    review_path,
    run_dir,
    runs_root,
    runtime_root,
    session_path,
    set_current_session,
)
from paperorchestra.core.session_snapshot import snapshot_inputs
from paperorchestra.core.session_storage import NOTES_RETAIN_COUNT, load_session, save_session


def create_session(cwd: str | Path | None, inputs: InputBundle, *, allow_outside_workspace: bool = False) -> SessionState:
    session_id = f"po-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()
    run_dir = runs_root(cwd) / session_id
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "build").mkdir(parents=True, exist_ok=True)
    (run_dir / "reviews").mkdir(parents=True, exist_ok=True)
    snapped_inputs = snapshot_inputs(cwd, run_dir, inputs, allow_outside_workspace=allow_outside_workspace)
    state = SessionState(
        session_id=session_id,
        created_at=now,
        updated_at=now,
        current_phase="outline_generation",
        active_artifact="outline.json",
        inputs=snapped_inputs,
        artifacts=ArtifactIndex(),
        notes=["Session initialized with snapshotted inputs."],
    )
    save_session(cwd, state)
    set_current_session(cwd, session_id)
    return state
