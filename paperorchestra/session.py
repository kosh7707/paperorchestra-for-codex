from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from .models import ArtifactIndex, InputBundle, SessionState, utc_now_iso

ROOT_DIRNAME = ".paper-orchestra"
CURRENT_FILE = "current_session.txt"
NOTES_RETAIN_COUNT = 20
_SESSION_IO_LOCK = threading.RLock()


def project_root(cwd: str | Path | None = None) -> Path:
    return Path(cwd or ".").resolve()


def runtime_root(cwd: str | Path | None = None) -> Path:
    root = project_root(cwd) / ROOT_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def runs_root(cwd: str | Path | None = None) -> Path:
    path = runtime_root(cwd) / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _snapshot_file(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination)


def _snapshot_inputs(cwd: str | Path | None, run_dir: Path, inputs: InputBundle, *, allow_outside_workspace: bool) -> InputBundle:
    root = project_root(cwd)
    inputs_dir = run_dir / "inputs"
    idea_source = Path(inputs.idea_path).resolve()
    experimental_source = Path(inputs.experimental_log_path).resolve()
    template_source = Path(inputs.template_path).resolve()
    guidelines_source = Path(inputs.guidelines_path).resolve()
    figures_source = Path(inputs.figures_dir).resolve() if inputs.figures_dir else None

    sources = [idea_source, experimental_source, template_source, guidelines_source]
    if figures_source:
        sources.append(figures_source)
    if not allow_outside_workspace:
        outside = [str(path) for path in sources if not _is_within(path, root)]
        if outside:
            raise ValueError(
                "Refusing to initialize session from paths outside the workspace without --allow-outside-workspace: "
                + ", ".join(outside)
            )

    snapped_figures = None
    if figures_source:
        snapped_figures_dir = inputs_dir / "figures"
        if snapped_figures_dir.exists():
            shutil.rmtree(snapped_figures_dir)
        shutil.copytree(figures_source, snapped_figures_dir)
        snapped_figures = str(snapped_figures_dir)

    return InputBundle(
        idea_path=_snapshot_file(idea_source, inputs_dir / "idea.md"),
        experimental_log_path=_snapshot_file(experimental_source, inputs_dir / "experimental_log.md"),
        template_path=_snapshot_file(template_source, inputs_dir / "template.tex"),
        guidelines_path=_snapshot_file(guidelines_source, inputs_dir / "conference_guidelines.md"),
        figures_dir=snapped_figures,
        cutoff_date=inputs.cutoff_date,
        venue=inputs.venue,
        page_limit=inputs.page_limit,
    )


def create_session(cwd: str | Path | None, inputs: InputBundle, *, allow_outside_workspace: bool = False) -> SessionState:
    session_id = f"po-{uuid.uuid4().hex[:12]}"
    now = utc_now_iso()
    run_dir = runs_root(cwd) / session_id
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "build").mkdir(parents=True, exist_ok=True)
    (run_dir / "reviews").mkdir(parents=True, exist_ok=True)
    snapped_inputs = _snapshot_inputs(cwd, run_dir, inputs, allow_outside_workspace=allow_outside_workspace)
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


def set_current_session(cwd: str | Path | None, session_id: str) -> None:
    (runtime_root(cwd) / CURRENT_FILE).write_text(session_id + "\n", encoding="utf-8")


def get_current_session_id(cwd: str | Path | None = None) -> str:
    path = runtime_root(cwd) / CURRENT_FILE
    if not path.exists():
        raise FileNotFoundError("No current PaperOrchestra session. Run `paperorchestra init` first.")
    return path.read_text(encoding="utf-8").strip()


def run_dir(cwd: str | Path | None, session_id: str | None = None) -> Path:
    session_id = session_id or get_current_session_id(cwd)
    path = runs_root(cwd) / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(cwd: str | Path | None, session_id: str | None = None) -> Path:
    return run_dir(cwd, session_id) / "session.json"


def load_session(cwd: str | Path | None, session_id: str | None = None) -> SessionState:
    path = session_path(cwd, session_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing session file: {path}")
    with _SESSION_IO_LOCK:
        return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_session(cwd: str | Path | None, state: SessionState) -> Path:
    path = session_path(cwd, state.session_id)
    if len(state.notes) > NOTES_RETAIN_COUNT:
        overflow = state.notes[:-NOTES_RETAIN_COUNT]
        state.notes_archive.extend(overflow)
        state.notes = state.notes[-NOTES_RETAIN_COUNT:]
    state.updated_at = utc_now_iso()
    with _SESSION_IO_LOCK:
        existing = None
        if path.exists():
            try:
                existing = SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                existing = None
        if existing is not None:
            for field_name in ("latest_prompt_trace_dir", "latest_provider_identity_json"):
                incoming_value = getattr(state.artifacts, field_name)
                existing_value = getattr(existing.artifacts, field_name)
                if incoming_value is None:
                    setattr(state.artifacts, field_name, existing_value)
                    continue
                if existing_value is None:
                    continue
                incoming_path = Path(incoming_value)
                existing_path = Path(existing_value)
                if existing_path.exists() and (
                    not incoming_path.exists() or existing_path.stat().st_mtime > incoming_path.stat().st_mtime
                ):
                    setattr(state.artifacts, field_name, existing_value)
            if state.latest_provider_name is None:
                state.latest_provider_name = existing.latest_provider_name
            if state.latest_runtime_mode is None:
                state.latest_runtime_mode = existing.latest_runtime_mode
        tmp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
        tmp_path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    return path


def artifact_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    path = run_dir(cwd, session_id) / "artifacts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def review_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    path = run_dir(cwd, session_id) / "reviews" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    path = run_dir(cwd, session_id) / "build" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
