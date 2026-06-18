from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.feedback.packet_artifacts import _file_sha256, _sha256_prefixed


def _stage_candidate_text_for_verification(cwd: str | Path | None, candidate_path: str | Path) -> str:
    state = load_session(cwd)
    candidate = Path(candidate_path).resolve()
    candidate_text = candidate.read_text(encoding="utf-8")
    state.artifacts.paper_full_tex = str(candidate)
    state.active_artifact = candidate.name
    save_session(cwd, state)
    return candidate_text


def _preserve_operator_candidate_for_attempt(
    cwd: str | Path | None,
    candidate_result: dict[str, Any],
    *,
    attempt_index: int,
) -> dict[str, Any]:
    candidate_path = candidate_result.get("candidate_path")
    if not candidate_path:
        return candidate_result
    source = Path(str(candidate_path)).resolve()
    if not source.exists() or not source.is_file():
        return candidate_result
    preserved = artifact_path(cwd, f"paper.operator-feedback.attempt-{attempt_index:02d}.candidate.tex")
    preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    updated = dict(candidate_result)
    updated.setdefault("raw_candidate_path", str(source))
    updated["candidate_path"] = str(preserved)
    updated["candidate_sha256"] = _sha256_prefixed(_file_sha256(preserved))
    updated["candidate_preservation_path"] = str(preserved)
    return updated


def _promote_candidate_text(cwd: str | Path | None, candidate_path: str | Path, canonical_path: str | Path | None) -> str:
    if not canonical_path:
        raise ContractError("cannot promote candidate without a canonical manuscript path")
    canonical = Path(canonical_path).resolve()
    candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    canonical.write_text(candidate_text, encoding="utf-8")
    state = load_session(cwd)
    state.artifacts.paper_full_tex = str(canonical)
    state.active_artifact = canonical.name
    save_session(cwd, state)
    return candidate_text
