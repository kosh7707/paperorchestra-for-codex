from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.ralph.state import _artifact_sha


def preserve_citation_candidate_for_approval(
    cwd: str | Path | None,
    candidate_path: str | Path | None,
) -> str | None:
    if not candidate_path:
        return None
    source = Path(candidate_path).resolve()
    if not source.exists() or not source.is_file():
        return str(source)
    digest = _artifact_sha(source)
    if not digest:
        return str(source)
    short = digest.split(":", 1)[-1][:16]
    preserved = artifact_path(cwd, f"paper.citation-repair.approval-{short}.candidate.tex")
    if not preserved.exists() or _artifact_sha(preserved) != digest:
        preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return str(preserved)
