from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from typing import Any

from paperorchestra.reviews.source_support_html import _collapse_ws, _html_attrs, _html_to_text

DISALLOWED_PDF_HOST_MARKERS = ("sci-hub", "researchgate", "semanticscholar", "archive", "mirror", "drive.google", "dropbox", "cdn")


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
        candidates.append(
            {
                "url": absolute,
                "label": label_text,
                "kind": kind,
                "priority": _pdf_candidate_priority(final_landing_url, absolute, label_text, kind),
            }
        )

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
