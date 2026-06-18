from __future__ import annotations

from pathlib import Path

ROOT_DIRNAME = ".paper-orchestra"
CURRENT_FILE = "current_session.txt"


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


def _run_child_path(cwd: str | Path | None, folder: str, name: str, session_id: str | None = None) -> Path:
    path = run_dir(cwd, session_id) / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def artifact_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    return _run_child_path(cwd, "artifacts", name, session_id)


def review_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    return _run_child_path(cwd, "reviews", name, session_id)


def build_path(cwd: str | Path | None, name: str, session_id: str | None = None) -> Path:
    return _run_child_path(cwd, "build", name, session_id)
