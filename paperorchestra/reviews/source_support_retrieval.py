from __future__ import annotations

import html
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from paperorchestra.reviews.citation_source_payload import _clean_optional_string


DISALLOWED_PDF_HOST_MARKERS = ("sci-hub", "researchgate", "semanticscholar", "archive", "mirror", "drive.google", "dropbox", "cdn")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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


def _download_source_evidence(
    cwd: str | Path | None,
    case: dict[str, Any],
    *,
    reference_case_dir: Callable[[str | Path | None, str], Path],
    run_relative_artifact_path: Callable[[str | Path | None, Path], str],
) -> dict[str, Any] | None:
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
        directory = reference_case_dir(cwd, str(case["id"]))
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
            evidence = {"status": "pdf", "path": run_relative_artifact_path(cwd, pdf), "url": url}
            if _extract_pdf_text(pdf, text_path):
                evidence["text"] = run_relative_artifact_path(cwd, text_path)
            return evidence
        if "text/html" in content_type or data.lstrip().startswith(b"<"):
            html_text = data.decode("utf-8", "replace")
            blocked_reason = _blocked_html_reason(final_url, html_text)
            if blocked_reason:
                return {"status": "blocked", "why": blocked_reason, "url": final_url}
            pdf_candidate_decisions = _candidate_pdf_links(final_url, html_text)
            selected_pdf = _download_pdf_candidate(cwd, directory, final_url, pdf_candidate_decisions, run_relative_artifact_path=run_relative_artifact_path)
            if selected_pdf is not None:
                return selected_pdf
            html_path = directory / "source.html"
            html_path.write_bytes(data)
            text_path = directory / "source.txt"
            text_path.write_text(_html_to_text(html_text), encoding="utf-8")
            return {
                "status": "html",
                "path": run_relative_artifact_path(cwd, html_path),
                "text": run_relative_artifact_path(cwd, text_path),
                "url": url,
                "_pdf_candidates": _public_pdf_candidate_decisions(pdf_candidate_decisions),
            }
        text_path = directory / "source.txt"
        text_path.write_text(data.decode("utf-8", "replace"), encoding="utf-8")
        return {"status": "text", "text": run_relative_artifact_path(cwd, text_path), "url": url}
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


def _download_pdf_candidate(
    cwd: str | Path | None,
    directory: Path,
    final_landing_url: str,
    candidates: list[dict[str, Any]],
    *,
    run_relative_artifact_path: Callable[[str | Path | None, Path], str],
) -> dict[str, Any] | None:
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
        selected = {"status": "pdf", "path": run_relative_artifact_path(cwd, pdf), "url": final_pdf_url, "_pdf_candidates": candidates}
        if _extract_pdf_text(pdf, text_path):
            selected["text"] = run_relative_artifact_path(cwd, text_path)
    if selected is not None:
        for candidate in candidates:
            if not candidate.get("decision"):
                candidate.update({"decision": "rejected", "reason": "lower_priority_pdf_candidate"})
        selected["_pdf_candidates"] = _public_pdf_candidate_decisions(candidates)
    return selected
