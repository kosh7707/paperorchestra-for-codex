from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session, save_session


def _snapshot_tree(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "files": [
            {"relative_path": item.relative_to(path).as_posix(), "content": item.read_bytes()}
            for item in sorted(path.rglob("*"))
            if item.is_file()
        ]
        if path.exists()
        else [],
    }


def _restore_tree(snapshot: dict[str, Any]) -> None:
    path_value = snapshot.get("path") if isinstance(snapshot, dict) else None
    if not path_value:
        return
    root = Path(path_value)
    if root.exists():
        shutil.rmtree(root)
    if not snapshot.get("exists"):
        return
    root.mkdir(parents=True, exist_ok=True)
    for item in snapshot.get("files") or []:
        if not isinstance(item, dict) or not item.get("relative_path"):
            continue
        target = root / str(item["relative_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.get("content") or b"")


def _session_snapshot(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    paper_path = Path(state.artifacts.paper_full_tex).resolve() if state.artifacts.paper_full_tex else None
    references_dir = artifact_path(cwd, "references")
    artifact_paths = []
    if paper_path:
        artifact_paths.extend(
            [
                paper_path.parent / "citation_support_review.json",
                paper_path.parent / "citation_support_review.trace.json",
                paper_path.parent / "citation_support_human_needed.md",
            ]
        )
    return {
        "state": state.to_dict(),
        "paper_path": str(paper_path) if paper_path else None,
        "paper_text": paper_path.read_text(encoding="utf-8") if paper_path and paper_path.exists() else None,
        "artifact_files": [
            {
                "path": str(path),
                "exists": path.exists(),
                "content": path.read_bytes() if path.exists() else None,
            }
            for path in artifact_paths
        ],
        "reference_tree": _snapshot_tree(references_dir),
    }


def _restore_session_snapshot(cwd: str | Path | None, snapshot: dict[str, Any]) -> None:
    from paperorchestra.core.models import SessionState

    paper_path = snapshot.get("paper_path")
    paper_text = snapshot.get("paper_text")
    if paper_path and paper_text is not None:
        Path(paper_path).write_text(paper_text, encoding="utf-8")
    for item in snapshot.get("artifact_files") or []:
        path_value = item.get("path") if isinstance(item, dict) else None
        if not path_value:
            continue
        path = Path(path_value)
        if item.get("exists"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(item.get("content") or b"")
        else:
            path.unlink(missing_ok=True)
    reference_tree = snapshot.get("reference_tree")
    if isinstance(reference_tree, dict):
        _restore_tree(reference_tree)
    state = SessionState.from_dict(snapshot["state"])
    save_session(cwd, state)


