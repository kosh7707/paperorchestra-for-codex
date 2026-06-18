from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.reviews.source_support_classifier import _classify_source_support
from paperorchestra.reviews.source_support_resolution import _reference_case_dir
from paperorchestra.reviews.source_support_retrieval import _download_source_evidence


def _run_relative_artifact_path(cwd: str | Path | None, path: Path) -> str:
    state = load_session(cwd)
    run_root = artifact_path(cwd, "_relative_anchor", session_id=state.session_id).parent.parent
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _write_source_meta(cwd: str | Path | None, case: dict[str, Any], evidence: dict[str, Any]) -> None:
    directory = _reference_case_dir(cwd, str(case["id"]))
    directory.mkdir(parents=True, exist_ok=True)
    source = case.get("source") if isinstance(case.get("source"), dict) else {}
    meta_evidence = _public_source_evidence(evidence)
    pdf_candidates = evidence.get("_pdf_candidates") if isinstance(evidence.get("_pdf_candidates"), list) else None
    if pdf_candidates:
        meta_evidence["pdf_candidates"] = pdf_candidates
    meta = {
        "schema": "citation-source-artifact/1",
        "case": str(case.get("id") or ""),
        "key": str(case.get("key") or ""),
        "source": source,
        "evidence": meta_evidence,
    }
    (directory / "source.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _public_source_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in evidence.items() if not str(key).startswith("_")}


def _existing_source_evidence(cwd: str | Path | None, case_id: str) -> dict[str, Any] | None:
    directory = _reference_case_dir(cwd, case_id)
    pdf = directory / "source.pdf"
    html_path = directory / "source.html"
    text = directory / "source.txt"
    if pdf.exists():
        evidence = {"status": "pdf", "path": _run_relative_artifact_path(cwd, pdf)}
        if text.exists():
            evidence["text"] = _run_relative_artifact_path(cwd, text)
        return evidence
    if html_path.exists():
        evidence = {"status": "html", "path": _run_relative_artifact_path(cwd, html_path)}
        if text.exists():
            evidence["text"] = _run_relative_artifact_path(cwd, text)
        return evidence
    if text.exists():
        return {"status": "text", "text": _run_relative_artifact_path(cwd, text)}
    return None


def _resolve_source_evidence(cwd: str | Path | None, case: dict[str, Any], *, ignore_existing_source: bool = False) -> dict[str, Any]:
    if not ignore_existing_source:
        existing = _existing_source_evidence(cwd, str(case["id"]))
        if existing is not None:
            _write_source_meta(cwd, case, existing)
            return _public_source_evidence(existing)
    downloaded = _download_source_evidence(
        cwd,
        case,
        reference_case_dir=_reference_case_dir,
        run_relative_artifact_path=_run_relative_artifact_path,
    )
    if downloaded is not None:
        _write_source_meta(cwd, case, downloaded)
        return _public_source_evidence(downloaded)
    source = case.get("source") if isinstance(case.get("source"), dict) else {}
    if source.get("url"):
        evidence = {"status": "missing", "why": "unretrieved"}
    else:
        evidence = {"status": "missing", "why": "no_locator"}
    _write_source_meta(cwd, case, evidence)
    return evidence


def _read_run_relative_text(cwd: str | Path | None, relative_path: str | None) -> str:
    if not relative_path:
        return ""
    state = load_session(cwd)
    run_root = artifact_path(cwd, "_relative_anchor", session_id=state.session_id).parent.parent
    path = Path(relative_path)
    if not path.is_absolute():
        path = run_root / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _inspect_source_case(case: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, str, str]:
    status = str(evidence.get("status") or "missing")
    if status in {"blocked", "missing"}:
        why = str(evidence.get("why") or status)
        ask = (
            f"Provide a PDF at artifacts/references/{case['id']}/source.pdf, "
            f"HTML/text at artifacts/references/{case['id']}/source.html or source.txt, "
            "an accessible official URL, a replacement citation, or approve weakening/removing the claim."
        )
        return "human_needed", "ask", ask if why == "unretrieved" else f"{why}: {ask}"
    cwd = case.get("_cwd")
    text = _read_run_relative_text(cwd, str(evidence.get("text") or "")) if cwd is not None else ""
    if not text.strip():
        ask = (
            f"Provide readable extracted text at artifacts/references/{case['id']}/source.txt, "
            "or replace/approve weakening the citation if the source cannot be read."
        )
        return "human_needed", "ask", ask
    verdict, note = _classify_source_support(case, text)
    return verdict, "note", note
