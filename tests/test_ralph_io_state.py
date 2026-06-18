from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import create_session
from paperorchestra.loop_engine.ralph.state import guarded_replace_manuscript_text, recover_pending_manuscript_write


def _inputs(root: Path) -> InputBundle:
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "idea_path": root / "idea.md",
        "experimental_log_path": root / "log.md",
        "template_path": root / "template.tex",
        "guidelines_path": root / "guidelines.md",
    }
    for path in files.values():
        path.write_text("content", encoding="utf-8")
    return InputBundle(**{key: str(path) for key, path in files.items()})


def test_guarded_manuscript_write_recovers_original_text(tmp_path: Path) -> None:
    create_session(tmp_path, _inputs(tmp_path / "materials"))
    paper = tmp_path / "paper.tex"
    paper.write_text("original", encoding="utf-8")

    marker_path = guarded_replace_manuscript_text(tmp_path, paper, "candidate", reason="test")
    assert marker_path.exists()
    assert paper.read_text(encoding="utf-8") == "candidate"

    result = recover_pending_manuscript_write(tmp_path)

    assert result["status"] == "restored_original"
    assert paper.read_text(encoding="utf-8") == "original"
    assert not marker_path.exists()
