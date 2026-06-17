from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.validator import CITE_COMMAND_RE
from paperorchestra.reviews.citation_sentences import _sentence_end, _sentence_start, extract_cited_sentences
from paperorchestra.reviews.citation_source_payload import _clean_optional_string, _lean_source_payload


DISALLOWED_PDF_HOST_MARKERS = ("sci-hub", "researchgate", "semanticscholar", "archive", "mirror", "drive.google", "dropbox", "cdn")


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


def _source_locators(source: dict[str, Any]) -> list[str]:
    locators: list[str] = []
    arxiv = _clean_optional_string(source.get("arxiv"))
    if arxiv:
        arxiv_id = re.sub(r"(?i)^arxiv:\s*", "", arxiv).strip()
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        if arxiv_id:
            locators.append(f"https://arxiv.org/pdf/{arxiv_id}.pdf")
            locators.append(f"https://arxiv.org/abs/{arxiv_id}")
    url = _clean_optional_string(source.get("url"))
    if url:
        locators.append(url)
    doi = _clean_optional_string(source.get("doi"))
    if doi:
        doi_value = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", doi).strip()
        if doi_value:
            locators.append(f"https://doi.org/{doi_value}")
    result: list[str] = []
    for locator in locators:
        if locator not in result:
            result.append(locator)
    return result


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


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _collapse_ws(html.unescape(text))


def _blocked_html_reason(final_url: str, html_value: str) -> str | None:
    visible_text = _html_to_text(html_value).lower()
    raw_text = html.unescape(html_value).lower()
    haystack = f"{visible_text} {raw_text}"

    def has_any(*markers: str) -> bool:
        return any(marker in haystack for marker in markers)

    article_context = has_any("article", "paper", "full text", "full-text", "download", "access")
    if has_any("captcha", "recaptcha", "hcaptcha", "verify you are human", "checking your browser"):
        return "captcha"
    if has_any("login required", "sign in to access", "log in to continue"):
        return "login_required"
    if "type=\"password\"" in raw_text or "type='password'" in raw_text:
        if article_context:
            return "login_required"
    if has_any("purchase access", "subscribe to access", "rent this article"):
        return "paywall"
    if has_any("institutional access", "access options", "get access") and has_any("article", "paper", "full text", "full-text"):
        return "paywall"
    if has_any("access denied", "request blocked", "bot protection", "automated traffic", "forbidden"):
        return "forbidden"
    return None


def _response_final_url(response: Any, requested_url: str) -> str:
    geturl = getattr(response, "geturl", None)
    if callable(geturl):
        try:
            value = str(geturl() or "").strip()
            if value:
                return value
        except Exception:
            pass
    return requested_url


def _html_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", tag):
        attrs[match.group(1).lower()] = html.unescape(match.group(2) or match.group(3) or match.group(4) or "")
    return attrs


def _candidate_pdf_links(final_landing_url: str, html_value: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(raw_url: str, *, label: str = "", kind: str = "link") -> None:
        raw_url = str(raw_url or "").strip()
        if not raw_url:
            return
        absolute = urllib.parse.urljoin(final_landing_url, html.unescape(raw_url))
        parsed = urllib.parse.urlparse(absolute)
        label_text = _collapse_ws(label)
        if not (parsed.path.lower().endswith(".pdf") or "pdf" in label_text.lower()):
            return
        if absolute in seen:
            return
        seen.add(absolute)
        candidates.append({"url": absolute, "label": label_text, "kind": kind, "priority": _pdf_candidate_priority(final_landing_url, absolute, label_text, kind)})

    for tag_match in re.finditer(r"(?is)<meta\b[^>]*>", html_value):
        attrs = _html_attrs(tag_match.group(0))
        name = (attrs.get("name") or attrs.get("property") or "").strip().lower()
        content = attrs.get("content") or ""
        if name in {"citation_pdf_url", "dc.identifier", "eprints.document_url"} or content.lower().endswith(".pdf"):
            add_candidate(content, label=name, kind="meta")

    for tag_match in re.finditer(r"(?is)<link\b[^>]*>", html_value):
        attrs = _html_attrs(tag_match.group(0))
        href = attrs.get("href") or ""
        rel = attrs.get("rel") or attrs.get("type") or ""
        if href and (href.lower().endswith(".pdf") or "pdf" in rel.lower()):
            add_candidate(href, label=rel, kind="link")

    for match in re.finditer(r"(?is)<a\b([^>]*)>(.*?)</a>", html_value):
        attrs = _html_attrs(match.group(1))
        href = attrs.get("href") or ""
        label = _html_to_text(match.group(2))
        add_candidate(href, label=label, kind="anchor")

    return sorted(candidates, key=lambda item: (int(item.get("priority") or 0), str(item.get("url") or "")))


def _pdf_candidate_priority(final_landing_url: str, candidate_url: str, label: str, kind: str) -> int:
    landing_stem = Path(urllib.parse.urlparse(final_landing_url).path.rstrip("/")).name.lower()
    candidate_name = Path(urllib.parse.urlparse(candidate_url).path).name.lower()
    candidate_stem = candidate_name[:-4] if candidate_name.endswith(".pdf") else candidate_name
    label_lower = label.lower()
    if kind == "meta":
        return 0
    if landing_stem and candidate_stem == landing_stem:
        return 1
    if label_lower in {"pdf", "download pdf", "article pdf", "full text pdf"}:
        return 2
    if "supplement" in candidate_name or "appendix" in candidate_name:
        return 20
    return 10


def _host(value: str) -> str:
    return (urllib.parse.urlparse(value).hostname or "").lower()


def _is_same_host_or_subdomain(parent_url: str, candidate_url: str) -> bool:
    parent_host = _host(parent_url)
    candidate_host = _host(candidate_url)
    if not parent_host or not candidate_host:
        return False
    return candidate_host == parent_host or candidate_host.endswith(f".{parent_host}")


def _has_disallowed_pdf_host(value: str) -> bool:
    host = _host(value)
    return any(marker in host for marker in DISALLOWED_PDF_HOST_MARKERS)


def _candidate_trust_rejection(final_landing_url: str, candidate_url: str) -> str | None:
    parsed = urllib.parse.urlparse(candidate_url)
    if parsed.scheme not in {"http", "https"}:
        return "unsupported_url_scheme"
    if _has_disallowed_pdf_host(candidate_url):
        return "disallowed_host"
    landing_host = _host(final_landing_url)
    candidate_host = _host(candidate_url)
    if landing_host == "arxiv.org" and candidate_host == "arxiv.org" and parsed.path.startswith("/pdf/"):
        return None
    if not _is_same_host_or_subdomain(final_landing_url, candidate_url):
        return "off_domain"
    return None


def _candidate_redirect_rejection(final_landing_url: str, final_pdf_url: str) -> str | None:
    if _has_disallowed_pdf_host(final_pdf_url):
        return "disallowed_host"
    landing_host = _host(final_landing_url)
    final_host = _host(final_pdf_url)
    parsed = urllib.parse.urlparse(final_pdf_url)
    if landing_host == "arxiv.org" and final_host == "arxiv.org" and parsed.path.startswith("/pdf/"):
        return None
    if not _is_same_host_or_subdomain(final_landing_url, final_pdf_url):
        return "redirect_off_domain"
    return None


def _extract_pdf_text(pdf_path: Path, text_path: Path) -> bool:
    if not shutil.which("pdftotext"):
        return False
    try:
        subprocess.run(["pdftotext", str(pdf_path), str(text_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except Exception:
        return False
    return text_path.exists() and text_path.stat().st_size > 0


def _download_source_evidence(cwd: str | Path | None, case: dict[str, Any]) -> dict[str, Any] | None:
    source = case.get("source") if isinstance(case.get("source"), dict) else {}
    locators = _source_locators(source)
    if not locators:
        return None
    last_result: dict[str, Any] | None = None
    for url in locators:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            last_result = {"status": "blocked", "why": "unsupported_url_scheme", "url": url}
            continue
        if parsed.hostname and parsed.hostname.endswith(".test"):
            continue
        directory = _reference_case_dir(cwd, str(case["id"]))
        directory.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "PaperOrchestra-reference-fetch/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(10_000_000 + 1)
                content_type = str(response.headers.get("Content-Type") or "").lower()
                final_url = _response_final_url(response, url)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                return {"status": "blocked", "why": "forbidden", "url": url}
            if exc.code == 404:
                last_result = {"status": "missing", "why": "not_found", "url": url}
                continue
            last_result = {"status": "missing", "why": "network_error", "url": url}
            continue
        except Exception:
            last_result = {"status": "missing", "why": "network_error", "url": url}
            continue
        if len(data) > 10_000_000:
            return {"status": "blocked", "why": "oversized", "url": url}
        if data.startswith(b"%PDF") or "application/pdf" in content_type:
            pdf = directory / "source.pdf"
            pdf.write_bytes(data)
            text_path = directory / "source.txt"
            evidence = {"status": "pdf", "path": _run_relative_artifact_path(cwd, pdf), "url": url}
            if _extract_pdf_text(pdf, text_path):
                evidence["text"] = _run_relative_artifact_path(cwd, text_path)
            return evidence
        if "text/html" in content_type or data.lstrip().startswith(b"<"):
            html_text = data.decode("utf-8", "replace")
            blocked_reason = _blocked_html_reason(final_url, html_text)
            if blocked_reason:
                return {"status": "blocked", "why": blocked_reason, "url": final_url}
            pdf_candidate_decisions = _candidate_pdf_links(final_url, html_text)
            selected_pdf = _download_pdf_candidate(cwd, directory, final_url, pdf_candidate_decisions)
            if selected_pdf is not None:
                return selected_pdf
            html_path = directory / "source.html"
            html_path.write_bytes(data)
            text_path = directory / "source.txt"
            text_path.write_text(_html_to_text(html_text), encoding="utf-8")
            return {
                "status": "html",
                "path": _run_relative_artifact_path(cwd, html_path),
                "text": _run_relative_artifact_path(cwd, text_path),
                "url": url,
                "_pdf_candidates": _public_pdf_candidate_decisions(pdf_candidate_decisions),
            }
        text_path = directory / "source.txt"
        text_path.write_text(data.decode("utf-8", "replace"), encoding="utf-8")
        return {"status": "text", "text": _run_relative_artifact_path(cwd, text_path), "url": url}
    return last_result


def _public_pdf_candidate_decisions(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in candidates:
        row = {
            "url": str(item.get("url") or ""),
            "decision": str(item.get("decision") or ""),
            "reason": str(item.get("reason") or ""),
        }
        if item.get("final_url"):
            row["final_url"] = str(item.get("final_url"))
        public.append(row)
    return public


def _download_pdf_candidate(cwd: str | Path | None, directory: Path, final_landing_url: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    selected: dict[str, Any] | None = None
    for candidate in candidates:
        candidate_url = str(candidate.get("url") or "")
        rejection = _candidate_trust_rejection(final_landing_url, candidate_url)
        if rejection:
            candidate.update({"decision": "rejected", "reason": rejection})
            continue
        if selected is not None:
            candidate.update({"decision": "rejected", "reason": "lower_priority_pdf_candidate"})
            continue
        request = urllib.request.Request(candidate_url, headers={"User-Agent": "PaperOrchestra-reference-fetch/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(10_000_000 + 1)
                content_type = str(response.headers.get("Content-Type") or "").lower()
                final_pdf_url = _response_final_url(response, candidate_url)
        except urllib.error.HTTPError as exc:
            candidate.update({"decision": "rejected", "reason": "forbidden" if exc.code in {401, 403} else "not_found" if exc.code == 404 else "network_error"})
            continue
        except Exception:
            candidate.update({"decision": "rejected", "reason": "network_error"})
            continue
        candidate["final_url"] = final_pdf_url
        redirect_rejection = _candidate_redirect_rejection(final_landing_url, final_pdf_url)
        if redirect_rejection:
            candidate.update({"decision": "rejected", "reason": redirect_rejection})
            continue
        if len(data) > 10_000_000:
            candidate.update({"decision": "rejected", "reason": "oversized"})
            continue
        if not (data.startswith(b"%PDF") or "application/pdf" in content_type):
            candidate.update({"decision": "rejected", "reason": "not_pdf"})
            continue
        candidate.update({"decision": "selected", "reason": "official_pdf"})
        pdf = directory / "source.pdf"
        pdf.write_bytes(data)
        text_path = directory / "source.txt"
        selected = {"status": "pdf", "path": _run_relative_artifact_path(cwd, pdf), "url": final_pdf_url, "_pdf_candidates": candidates}
        if _extract_pdf_text(pdf, text_path):
            selected["text"] = _run_relative_artifact_path(cwd, text_path)
    if selected is not None:
        for candidate in candidates:
            if not candidate.get("decision"):
                candidate.update({"decision": "rejected", "reason": "lower_priority_pdf_candidate"})
        selected["_pdf_candidates"] = _public_pdf_candidate_decisions(candidates)
    return selected


def _resolve_source_evidence(cwd: str | Path | None, case: dict[str, Any], *, ignore_existing_source: bool = False) -> dict[str, Any]:
    if not ignore_existing_source:
        existing = _existing_source_evidence(cwd, str(case["id"]))
        if existing is not None:
            _write_source_meta(cwd, case, existing)
            return _public_source_evidence(existing)
    downloaded = _download_source_evidence(cwd, case)
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


def _meaningful_terms(text: str) -> set[str]:
    return set(_meaningful_term_sequence(text))


def _meaningful_term_sequence(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "uses",
        "use",
        "using",
        "for",
        "into",
        "also",
        "show",
        "shows",
        "describe",
        "describes",
        "discuss",
        "discusses",
        "guide",
        "guides",
        "guided",
        "systems",
        "system",
        "model",
        "models",
    }
    terms: list[str] = []
    for raw in re.findall(r"[a-z0-9]{3,}", text.lower()):
        term = raw
        if len(term) > 4 and term.endswith("ies"):
            term = term[:-3] + "y"
        elif len(term) > 3 and term.endswith("s"):
            term = term[:-1]
        if term not in stop and term not in terms:
            terms.append(term)
    return terms


def _source_text_windows(text: str) -> list[str]:
    windows = [_collapse_ws(part) for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if _collapse_ws(part)]
    return windows or [_collapse_ws(text)]


def _cited_key_terms(case: dict[str, Any]) -> set[str]:
    keys = {str(case.get("key") or "")}
    for match in CITE_COMMAND_RE.finditer(str(case.get("anchor") or "")):
        keys.update(item.strip() for item in match.group(2).split(",") if item.strip())
    return {term for key in keys for term in _meaningful_term_sequence(key)}


def _target_subject_terms(case: dict[str, Any], target_terms: set[str]) -> set[str]:
    key_terms = set(_meaningful_term_sequence(str(case.get("key") or "")))
    subject = key_terms & target_terms
    if subject:
        return subject
    sequence = _meaningful_term_sequence(str(case.get("target") or ""))
    return {sequence[0]} if sequence else set()


def _relation_pass_threshold(relation_terms: set[str]) -> int:
    count = len(relation_terms)
    if count <= 2:
        return count
    return max(2, math.ceil(0.70 * count))


def _window_has_in_scope_contradiction(window: str, subject_terms: set[str], relation_terms: set[str]) -> bool:
    terms = _meaningful_terms(window)
    if subject_terms and not (subject_terms & terms):
        return False
    if len(relation_terms & terms) < min(2, len(relation_terms)):
        return False
    lower = window.lower()
    lower = lower.replace("not only", "").replace("not merely", "")
    markers = (
        "does not",
        "do not",
        "did not",
        "is not",
        "are not",
        "not use",
        "not uses",
        "without",
        "no evidence",
        "fails to",
        "unrelated to",
        "contradicts",
    )
    return any(marker in lower for marker in markers)


def _classify_source_support(case: dict[str, Any], source_text: str) -> tuple[str, str]:
    target_terms = _meaningful_terms(str(case.get("target") or ""))
    if not target_terms:
        return "weak", "The retrieved source artifact is available, but the target claim could not be isolated."
    subject_terms = _target_subject_terms(case, target_terms)
    cited_key_terms = _cited_key_terms(case)
    relation_terms = set(target_terms) - subject_terms - cited_key_terms
    threshold = _relation_pass_threshold(relation_terms)
    best_overlap = 0
    pass_found = False
    for window in _source_text_windows(source_text):
        window_terms = _meaningful_terms(window)
        relation_overlap = len(relation_terms & window_terms)
        best_overlap = max(best_overlap, relation_overlap)
        if _window_has_in_scope_contradiction(window, subject_terms, relation_terms):
            return "fail", "The retrieved source artifact appears to contradict the target claim."
        has_subject = bool(subject_terms & window_terms) if subject_terms else True
        if has_subject and relation_overlap >= threshold:
            pass_found = True
    if pass_found:
        return "pass", "The retrieved source artifact locally supports the target claim."
    if best_overlap or (_meaningful_terms(source_text) & target_terms):
        return "weak", "The retrieved source artifact is related, but local support for the target claim is partial."
    return "weak", "A source artifact was available, but local support for the target claim was not found."


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
