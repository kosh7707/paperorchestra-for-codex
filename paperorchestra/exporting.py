from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .session import artifact_path, load_session, run_dir


def _copy_if_present(label: str, source: str | None, destination: Path, copied: list[dict[str, str]], skipped: list[dict[str, str]]) -> None:
    if not source:
        skipped.append({"label": label, "reason": "not recorded"})
        return
    source_path = Path(source)
    if not source_path.exists():
        skipped.append({"label": label, "source": str(source_path), "reason": "missing on disk"})
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    copied.append({"label": label, "source": str(source_path), "destination": str(destination)})


def _session_artifact_dir(cwd: Path, state: Any) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent
    return run_dir(cwd, state.session_id) / "artifacts"


def export_current_artifacts(cwd: str | Path, output: str | Path, *, include_all_artifacts: bool = False) -> dict[str, object]:
    root = Path(cwd).resolve()
    state = load_session(root)
    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    artifacts = state.artifacts
    export_map = [
        ("paper_full_tex", artifacts.paper_full_tex, output_dir / "paper.full.tex"),
        ("compiled_pdf", artifacts.compiled_pdf, output_dir / "paper.full.pdf"),
        ("references_bib", artifacts.references_bib, output_dir / "references.bib"),
        ("latest_review_json", artifacts.latest_review_json, output_dir / "review.latest.json"),
        ("quality_gate_report", str(artifact_path(root, "quality-gate.report.json")), output_dir / "quality-gate.report.json"),
        ("session_json", str(run_dir(root, state.session_id) / "session.json"), output_dir / "session.json"),
    ]
    for label, source, destination in export_map:
        _copy_if_present(label, source, destination, copied, skipped)

    if include_all_artifacts:
        artifact_dir = _session_artifact_dir(root, state)
        if artifact_dir.exists():
            shutil.copytree(artifact_dir, output_dir / "artifacts", dirs_exist_ok=True)
            copied.append({"label": "artifacts_dir", "source": str(artifact_dir), "destination": str(output_dir / "artifacts")})
        else:
            skipped.append({"label": "artifacts_dir", "source": str(artifact_dir), "reason": "missing on disk"})

    return {"status": "ok", "session_id": state.session_id, "output_dir": str(output_dir), "copied": copied, "skipped": skipped}
