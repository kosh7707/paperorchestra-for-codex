from __future__ import annotations

import urllib.parse

DISALLOWED_PDF_HOST_MARKERS = ("sci-hub", "researchgate", "semanticscholar", "archive", "mirror", "drive.google", "dropbox", "cdn")


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
