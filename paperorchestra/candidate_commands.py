from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .models import utc_now_iso
from .pipeline import ContractError, compile_current_paper, record_current_validation_report
from .session import artifact_path, load_session, runtime_root, save_session


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _candidate_id(path: Path) -> str:
    digest = _file_sha256(path) or hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return f"cand-{digest[:12]}"


def _candidate_record(path: Path, *, source: str, source_execution_path: str | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "id": _candidate_id(resolved),
        "path": str(resolved),
        "filename": resolved.name,
        "sha256": "sha256:" + (_file_sha256(resolved) or ""),
        "source": source,
        "source_execution_path": source_execution_path,
    }


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _approval_candidate(payload: dict[str, Any]) -> str | None:
    approval = payload.get("candidate_approval")
    if isinstance(approval, dict) and approval.get("status") == "human_needed_candidate_ready":
        candidate_path = approval.get("candidate_path")
        return str(candidate_path) if candidate_path else None
    candidate_result = payload.get("candidate_result")
    if isinstance(candidate_result, dict):
        nested = candidate_result.get("candidate_approval")
        if isinstance(nested, dict) and nested.get("status") == "human_needed_candidate_ready":
            candidate_path = nested.get("candidate_path")
            return str(candidate_path) if candidate_path else None
    return None


def candidate_list(cwd: str | Path | None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for execution_path in sorted(runtime_root(cwd).glob("qa-loop-execution.iter-*.json")):
        payload = _read_json_if_exists(execution_path)
        candidate_path = _approval_candidate(payload) if isinstance(payload, dict) else None
        if candidate_path and Path(candidate_path).exists():
            resolved = Path(candidate_path).resolve()
            seen.add(resolved)
            records.append(_candidate_record(resolved, source="candidate_approval", source_execution_path=str(execution_path)))
    operator_execution = artifact_path(cwd, "operator_feedback.execution.json")
    payload = _read_json_if_exists(operator_execution)
    candidate_path = _approval_candidate(payload) if isinstance(payload, dict) else None
    if candidate_path and Path(candidate_path).exists():
        resolved = Path(candidate_path).resolve()
        if resolved not in seen:
            seen.add(resolved)
            records.append(_candidate_record(resolved, source="candidate_approval", source_execution_path=str(operator_execution)))
    artifact_dir = artifact_path(cwd, "paper.full.tex").parent
    for candidate in sorted(artifact_dir.glob("*.candidate.tex")):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        records.append(_candidate_record(resolved, source="candidate_file"))
    return {"schema_version": "candidate-list/1", "candidates": records}


def _resolve_candidate(cwd: str | Path | None, selector: str) -> dict[str, Any]:
    direct = Path(selector).expanduser()
    if direct.exists() and direct.is_file():
        return _candidate_record(direct.resolve(), source="direct_path")
    matches = []
    for record in candidate_list(cwd)["candidates"]:
        path = Path(record["path"])
        if selector in {record["id"], record["sha256"], record["sha256"].replace("sha256:", ""), path.name, path.stem}:
            matches.append(record)
    if not matches:
        raise ContractError(f"candidate not found: {selector}")
    if len(matches) > 1:
        raise ContractError(f"candidate selector is ambiguous: {selector}")
    return matches[0]


def candidate_diff(cwd: str | Path | None, selector: str) -> str:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before diffing a candidate.")
    current_path = Path(state.artifacts.paper_full_tex).resolve()
    record = _resolve_candidate(cwd, selector)
    candidate_path = Path(record["path"]).resolve()
    current = current_path.read_text(encoding="utf-8").splitlines(keepends=True)
    candidate = candidate_path.read_text(encoding="utf-8").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            current,
            candidate,
            fromfile=str(current_path),
            tofile=str(candidate_path),
        )
    )


def _append_decision(cwd: str | Path | None, payload: dict[str, Any]) -> Path:
    path = artifact_path(cwd, "candidate-decisions.jsonl")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def candidate_apply(cwd: str | Path | None, selector: str, *, as_author_approved: bool = False) -> dict[str, Any]:
    if not as_author_approved:
        raise ContractError("candidate-apply requires --as-author-approved")
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before applying a candidate.")
    record = _resolve_candidate(cwd, selector)
    candidate_path = Path(record["path"]).resolve()
    candidate_text = candidate_path.read_text(encoding="utf-8")
    current_path = Path(state.artifacts.paper_full_tex).resolve()
    canonical_path = artifact_path(cwd, "paper.full.tex").resolve()
    targets = []
    for target in (current_path, canonical_path):
        if target not in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(candidate_text, encoding="utf-8")
            targets.append(target)
    state.artifacts.paper_full_tex = str(canonical_path)
    state.active_artifact = canonical_path.name
    state.notes.append(f"Candidate applied with author approval: {candidate_path.name}")
    save_session(cwd, state)
    validation_path, validation_payload = record_current_validation_report(cwd, name="validation.candidate-apply.json")
    try:
        pdf_path = compile_current_paper(cwd)
        compile_payload = {"ok": True, "pdf": str(pdf_path)}
    except Exception as exc:
        compile_payload = {"ok": False, "error": str(exc)}
    decision = {
        "schema_version": "candidate-decision/1",
        "decided_at": utc_now_iso(),
        "decision": "applied",
        "candidate": record,
        "targets": [str(target) for target in targets],
        "validation": {"path": str(validation_path), "ok": validation_payload.get("ok")},
        "compile": compile_payload,
        "authority": "author_approved",
    }
    decision["decision_log"] = str(_append_decision(cwd, decision))
    return {"status": "applied", **decision}


def candidate_reject(cwd: str | Path | None, selector: str, *, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ContractError("candidate-reject requires --reason")
    record = _resolve_candidate(cwd, selector)
    decision = {
        "schema_version": "candidate-decision/1",
        "decided_at": utc_now_iso(),
        "decision": "rejected",
        "candidate": record,
        "reason": reason,
    }
    decision["decision_log"] = str(_append_decision(cwd, decision))
    return {"status": "rejected", **decision}
