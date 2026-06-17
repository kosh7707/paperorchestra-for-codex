from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.validator import CITE_COMMAND_RE
from paperorchestra.reviews.citation_sentences import _sentence_end, _sentence_start, extract_cited_sentences
from paperorchestra.reviews.citation_source_payload import _clean_optional_string, _lean_source_payload
from paperorchestra.reviews.source_support_classifier import _classify_source_support
from paperorchestra.reviews.source_support_retrieval import (
    _download_source_evidence,
    _source_locators,
)


def _strip_cites(text: str) -> str:
    return re.sub(CITE_COMMAND_RE, "", text).replace("~", " ")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentence_for_cite_in_paragraph(paragraph: str, cite_start: int, cite_end: int) -> str:
    start = _sentence_start(paragraph, cite_start)
    end = _sentence_end(paragraph, cite_end)
    return _collapse_ws(paragraph[start:end])


def _looks_like_section_heading(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return bool(stripped and len(stripped) < 80 and stripped.endswith(".") and "\\cite" not in stripped)


def _run_relative_artifact_path(cwd: str | Path | None, path: Path) -> str:
    state = load_session(cwd)
    run_root = artifact_path(cwd, "_relative_anchor", session_id=state.session_id).parent.parent
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def build_source_backed_citation_cases(
    cwd: str | Path | None,
    *,
    resolve_evidence: bool = True,
) -> list[dict[str, Any]]:
    """Build lean per-citation cases from the current manuscript.

    This is the source-backed v3 surface.  Cases are derived from the actual
    manuscript, not from the planning artifact: one case per citation key, with
    paragraph context plus a sentence anchor and target claim span.
    """

    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before citation support review.")
    latex = Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8")
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    body = _citation_review_body(latex)
    raw_paragraphs = [_collapse_ws(part) for part in re.split(r"\n\s*\n+", body) if _collapse_ws(part)]
    current_section = "Manuscript"
    paragraph_index = 0
    cases: list[dict[str, Any]] = []
    for paragraph in raw_paragraphs:
        if "\\cite" not in paragraph and _looks_like_section_heading(paragraph):
            current_section = paragraph.rstrip(".")
            continue
        if "\\cite" not in paragraph:
            continue
        paragraph_index += 1
        for cite_command_index, match in enumerate(CITE_COMMAND_RE.finditer(paragraph), start=1):
            raw_keys = [item.strip() for item in match.group(2).split(",") if item.strip()]
            anchor = _sentence_for_cite_in_paragraph(paragraph, match.start(), match.end())
            target = _collapse_ws(_strip_cites(anchor)).rstrip(".")
            for key in raw_keys:
                case_id = f"C{len(cases) + 1}"
                case: dict[str, Any] = {
                    "id": case_id,
                    "key": key,
                    "loc": f"{current_section} ¶{paragraph_index}",
                    "paragraph": paragraph,
                    "anchor": anchor,
                    "target": target,
                    "source": _lean_source_payload(key, citation_map),
                }
                if resolve_evidence:
                    case["_cwd"] = cwd
                    ignore_existing_source = _apply_human_resolution(cwd, case, citation_map)
                    if not case.get("_skip_source_resolution"):
                        evidence = _resolve_source_evidence(cwd, case, ignore_existing_source=ignore_existing_source)
                        case["evidence"] = evidence
                        verdict, message_field, message = _inspect_source_case(case, evidence)
                        case["verdict"] = verdict
                        case[message_field] = message
                cases.append(case)
    return cases


def _reference_case_dir(cwd: str | Path | None, case_id: str) -> Path:
    return artifact_path(cwd, f"references/{case_id}/source.meta.json").parent


def _human_resolution_path(cwd: str | Path | None, case_id: str) -> Path:
    return _reference_case_dir(cwd, case_id) / "human-resolution.json"


def _load_human_resolution(cwd: str | Path | None, case: dict[str, Any]) -> dict[str, Any] | None:
    path = _human_resolution_path(cwd, str(case.get("id") or ""))
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return {"action": "invalid", "status": "invalid", "reason": "unreadable_resolution"}
    if not isinstance(payload, dict):
        return {"action": "invalid", "status": "invalid", "reason": "invalid_resolution"}
    if payload.get("schema") != "citation-human-resolution/1":
        return {"action": "invalid", "status": "invalid", "reason": "invalid_schema"}
    if str(payload.get("case") or "") != str(case.get("id") or ""):
        return {"action": "invalid", "status": "invalid", "reason": "case_mismatch"}
    action = str(payload.get("action") or "").strip()
    if action not in {"provide_source_url", "replace_citation", "weaken_claim", "remove_claim"}:
        return {"action": action or "invalid", "status": "invalid", "reason": "unsupported_action"}
    return payload


def _mark_invalid_human_resolution(case: dict[str, Any], resolution: dict[str, Any]) -> None:
    case["resolution"] = resolution
    case["_skip_source_resolution"] = True
    case["evidence"] = {"status": "missing", "why": str(resolution.get("reason") or "invalid_resolution")}
    case["verdict"] = "human_needed"
    case["ask"] = "Fix artifacts/references/{}/human-resolution.json or provide source.pdf/html/txt.".format(case.get("id"))


def _apply_human_resolution(cwd: str | Path | None, case: dict[str, Any], citation_map: dict[str, Any]) -> bool:
    """Apply a per-case human citation resolution.

    Returns True when evidence resolution must ignore pre-existing case-local
    source artifacts so stale source.txt/pdf/html cannot mask a human-provided
    URL or replacement citation.
    """

    resolution = _load_human_resolution(cwd, case)
    if resolution is None:
        return False
    action = str(resolution.get("action") or "")
    if resolution.get("status") == "invalid":
        _mark_invalid_human_resolution(case, resolution)
        return False
    if action == "provide_source_url":
        url = _clean_optional_string(resolution.get("url"))
        parsed = urllib.parse.urlparse(url or "")
        if not url or parsed.scheme not in {"http", "https"}:
            _mark_invalid_human_resolution(case, {"action": action, "status": "invalid", "reason": "invalid_url"})
            return False
        original_source = case.get("source") if isinstance(case.get("source"), dict) else {}
        source = {
            key: value
            for key, value in original_source.items()
            if key not in {"url", "doi", "arxiv"}
        }
        source["url"] = url
        case["source"] = source
        case["resolution"] = {"action": action, "status": "applied", "url": url}
        return True
    if action == "replace_citation":
        replacement_key = _clean_optional_string(resolution.get("replacement_key"))
        raw_map = citation_map if isinstance(citation_map, dict) else {}
        if not replacement_key or replacement_key not in raw_map:
            _mark_invalid_human_resolution(
                case,
                {"action": action, "status": "invalid", "reason": "unknown_replacement_key", "replacement_key": replacement_key or ""},
            )
            return False
        original_key = str(case.get("key") or "")
        case["key"] = replacement_key
        case["source"] = _lean_source_payload(replacement_key, raw_map)
        case["resolution"] = {
            "action": action,
            "status": "applied",
            "original_key": original_key,
            "replacement_key": replacement_key,
        }
        if resolution.get("use_provided_source") is True:
            case["resolution"]["source"] = "provided"
            return False
        return True
    if action == "weaken_claim":
        target = _clean_optional_string(resolution.get("target"))
        if not target:
            _mark_invalid_human_resolution(case, {"action": action, "status": "invalid", "reason": "missing_target"})
            return False
        original_target = str(case.get("target") or "")
        case["target"] = target
        case["resolution"] = {
            "action": action,
            "status": "applied",
            "original_target": original_target,
            "target": target,
        }
        return False
    if action == "remove_claim":
        case["resolution"] = {
            "action": action,
            "status": "requires_manuscript_edit",
            "reason": _clean_optional_string(resolution.get("reason")) or "claim_removal_requested",
        }
        case["_skip_source_resolution"] = True
        case["evidence"] = {"status": "missing", "why": "claim_removal_requested"}
        case["verdict"] = "human_needed"
        case["ask"] = "Remove the unsupported claim/citation from the manuscript, then rerun citation review."
        return False
    return False


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


def _source_review_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
    for case in cases:
        verdict = str(case.get("verdict") or "human_needed")
        if verdict not in summary:
            verdict = "human_needed"
        summary[verdict] += 1
    return summary


def _short_markdown_value(value: Any, *, limit: int = 240) -> str:
    text = _collapse_ws(str(value or ""))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_citation_support_human_needed_markdown(review: dict[str, Any]) -> str | None:
    if review.get("schema") != "citation-support-review/3":
        return None
    cases = [
        case
        for case in review.get("cases") or []
        if isinstance(case, dict) and str(case.get("verdict") or "").strip().lower() == "human_needed"
    ]
    if not cases:
        return None
    lines = [
        "# Citation source follow-up",
        "",
        "Add the missing source artifact, then rerun `paperorchestra critique --citation-evidence-mode source`.",
        "",
    ]
    for case in cases:
        source = case.get("source") if isinstance(case.get("source"), dict) else {}
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        title = _short_markdown_value(source.get("title") or case.get("key"), limit=160)
        url = _short_markdown_value(source.get("url"), limit=180)
        reason = _short_markdown_value(evidence.get("why") or evidence.get("status") or "missing", limit=120)
        lines.extend(
            [
                f"## {case.get('id', '?')} — `{case.get('key', '?')}`",
                f"- Location: {_short_markdown_value(case.get('loc'), limit=120)}",
                f"- Paragraph: {_short_markdown_value(case.get('paragraph'), limit=360)}",
                f"- Anchor: {_short_markdown_value(case.get('anchor'), limit=300)}",
                f"- Target: {_short_markdown_value(case.get('target'), limit=300)}",
                f"- Source: {title}" + (f" ({url})" if url else ""),
                f"- Problem: {reason}",
                f"- Ask: {_short_markdown_value(case.get('ask'), limit=300)}",
                f"- Resolution file: `artifacts/references/{case.get('id', '?')}/human-resolution.json`",
                "- Resolution examples: `provide_source_url`, `replace_citation`, `weaken_claim`, or `remove_claim`.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_source_backed_citation_support_review(cwd: str | Path | None, *, mode: str = "source") -> dict[str, Any]:
    cases = build_source_backed_citation_cases(cwd, resolve_evidence=True)
    public_cases: list[dict[str, Any]] = []
    for case in cases:
        case = dict(case)
        case.pop("_cwd", None)
        case.pop("_skip_source_resolution", None)
        public_cases.append(case)
    return {
        "schema": "citation-support-review/3",
        "mode": mode,
        "summary": _source_review_summary(public_cases),
        "cases": public_cases,
    }


def build_citation_source_retrieval_debug(cwd: str | Path | None) -> dict[str, Any]:
    cases = build_source_backed_citation_cases(cwd, resolve_evidence=False)
    items: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for case in cases:
        evidence = _resolve_source_evidence(cwd, case)
        status = str(evidence.get("status") or "missing")
        summary[status] = summary.get(status, 0) + 1
        source = case.get("source") if isinstance(case.get("source"), dict) else {}
        items.append(
            {
                "id": case.get("id"),
                "key": case.get("key"),
                "source": source,
                "candidate_locators": _source_locators(source),
                "evidence": evidence,
            }
        )
    return {
        "schema": "citation-source-retrieval-debug/1",
        "summary": dict(sorted(summary.items())),
        "items": items,
    }


def write_citation_source_retrieval_debug(cwd: str | Path | None, output_path: str | Path | None = None) -> Path:
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "citation_source_retrieval_debug.json")
    path.write_text(json.dumps(build_citation_source_retrieval_debug(cwd), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
