from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from paperorchestra.reviews.source_support_candidates import (
    _blocked_html_reason,
    _candidate_pdf_links,
    _html_to_text,
    _public_pdf_candidate_decisions,
    _response_final_url,
)
from paperorchestra.reviews.citation_source_fields import _clean_optional_string
from paperorchestra.reviews.source_support_pdf_download import (
    _MAX_SOURCE_BYTES,
    _USER_AGENT,
    _download_pdf_candidate,
    _extract_pdf_text,
)


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
    return list(dict.fromkeys(locators))


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
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = response.read(_MAX_SOURCE_BYTES + 1)
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
        if len(data) > _MAX_SOURCE_BYTES:
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
            selected_pdf = _download_pdf_candidate(
                cwd,
                directory,
                final_url,
                pdf_candidate_decisions,
                run_relative_artifact_path=run_relative_artifact_path,
            )
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
