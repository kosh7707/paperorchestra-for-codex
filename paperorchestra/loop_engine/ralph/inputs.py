from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.ralph.state import _read_json


def _current_manuscript_hash(cwd: str | Path | None) -> tuple[str | None, str | None]:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        return None, None
    paper = Path(state.artifacts.paper_full_tex)
    if not paper.exists():
        return None, None
    bare = hashlib.sha256(paper.read_bytes()).hexdigest()
    return bare, f"sha256:{bare}"


def _load_explicit_quality_eval(cwd: str | Path | None, path: str | Path) -> tuple[Path, dict[str, Any]]:
    quality_path = Path(path).resolve()
    payload = _read_json(quality_path)
    if not isinstance(payload, dict):
        raise ValueError(f"quality-eval input is not a JSON object: {quality_path}")
    _, expected = _current_manuscript_hash(cwd)
    if payload.get("manuscript_hash") != expected:
        raise ValueError(
            "quality-eval input is stale for the current manuscript: "
            f"{quality_path} has {payload.get('manuscript_hash')!r}, expected {expected!r}"
        )
    return quality_path, payload


def _load_explicit_qa_loop_plan(cwd: str | Path | None, path: str | Path) -> dict[str, Any]:
    plan_path = Path(path).resolve()
    payload = _read_json(plan_path)
    if not isinstance(payload, dict):
        raise ValueError(f"qa-loop-plan input is not a JSON object: {plan_path}")
    _, expected = _current_manuscript_hash(cwd)
    summary = payload.get("quality_eval_summary") if isinstance(payload.get("quality_eval_summary"), dict) else {}
    if summary.get("manuscript_hash") != expected:
        raise ValueError(
            "qa-loop-plan input is stale for the current manuscript: "
            f"{plan_path} has {summary.get('manuscript_hash')!r}, expected {expected!r}"
        )
    return payload


def _split_path_ref(ref: Any) -> tuple[Path | None, str | None]:
    if not isinstance(ref, str) or not ref:
        return None, None
    path_text, sep, sha = ref.partition("@sha256:")
    return (Path(path_text).resolve() if path_text else None), (sha if sep else None)


def _quality_eval_path_from_plan(plan: dict[str, Any]) -> str | None:
    source_artifacts = plan.get("source_artifacts") if isinstance(plan.get("source_artifacts"), dict) else {}
    if source_artifacts.get("quality_eval"):
        return str(source_artifacts["quality_eval"])
    reads = plan.get("reads") if isinstance(plan.get("reads"), dict) else {}
    path, _ = _split_path_ref(reads.get("quality_eval"))
    return str(path) if path else None


def _validate_plan_quality_eval_identity(plan: dict[str, Any], quality_eval_path: Path) -> None:
    expected_sha = hashlib.sha256(quality_eval_path.read_bytes()).hexdigest()
    source_artifacts = plan.get("source_artifacts") if isinstance(plan.get("source_artifacts"), dict) else {}
    source_quality_eval = source_artifacts.get("quality_eval")
    if source_quality_eval and Path(str(source_quality_eval)).resolve() != quality_eval_path.resolve():
        raise ValueError(f"qa-loop-plan input references a different quality-eval artifact: {source_quality_eval}")
    reads = plan.get("reads") if isinstance(plan.get("reads"), dict) else {}
    read_path, read_sha = _split_path_ref(reads.get("quality_eval"))
    if read_path and read_path != quality_eval_path.resolve():
        raise ValueError(f"qa-loop-plan input references a different quality-eval artifact: {read_path}")
    if read_sha and read_sha != expected_sha:
        raise ValueError(f"qa-loop-plan input is stale for the provided quality-eval artifact: {quality_eval_path}")


def _default_citation_support_review_path(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _stage_explicit_citation_support_review(cwd: str | Path | None, path: str | Path | None) -> Path | None:
    if not path:
        return None
    source = Path(path).resolve()
    payload = _read_json(source)
    if not isinstance(payload, dict):
        raise ValueError(f"citation-support review input is not a JSON object: {source}")
    expected_bare, _ = _current_manuscript_hash(cwd)
    observed = payload.get("manuscript_sha256")
    if observed != expected_bare:
        raise ValueError(
            "citation-support review input is stale for the current manuscript: "
            f"{source} has {observed!r}, expected {expected_bare!r}"
        )
    target = _default_citation_support_review_path(cwd)
    if source != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        source_trace = source.with_name(source.stem + ".trace.json")
        if source_trace.exists():
            shutil.copyfile(source_trace, target.with_name(target.stem + ".trace.json"))
    return source


