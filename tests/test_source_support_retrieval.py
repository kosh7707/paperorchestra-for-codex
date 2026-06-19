from __future__ import annotations

from paperorchestra.reviews.source_support_retrieval import _candidate_pdf_links
from paperorchestra.reviews.source_support_pdf_trust import (
    _candidate_redirect_rejection,
    _candidate_trust_rejection,
)


def test_candidate_pdf_links_prefers_meta_pdf_and_dedupes_absolute_urls() -> None:
    html = """
    <html><head>
      <meta name="citation_pdf_url" content="/paper.pdf">
      <link rel="alternate application/pdf" href="/paper.pdf">
    </head><body>
      <a href="/supplement.pdf">Supplement PDF</a>
      <a href="/paper.pdf">Download PDF</a>
    </body></html>
    """

    candidates = _candidate_pdf_links("https://example.org/articles/paper", html)

    assert [item["url"] for item in candidates] == [
        "https://example.org/paper.pdf",
        "https://example.org/supplement.pdf",
    ]
    assert candidates[0]["kind"] == "meta"
    assert candidates[0]["priority"] == 0


def test_candidate_trust_rejects_off_domain_and_disallowed_hosts() -> None:
    assert _candidate_trust_rejection("https://example.org/paper", "https://downloads.example.org/paper.pdf") is None
    assert _candidate_trust_rejection("https://example.org/paper", "https://cdn.example.org/paper.pdf") == "disallowed_host"
    assert _candidate_trust_rejection("https://example.org/paper", "ftp://example.org/paper.pdf") == "unsupported_url_scheme"
    assert _candidate_trust_rejection("https://example.org/paper", "https://evil.test/paper.pdf") == "off_domain"
    assert _candidate_trust_rejection("https://example.org/paper", "https://researchgate.net/paper.pdf") == "disallowed_host"


def test_candidate_redirect_rejection_allows_arxiv_pdf_special_case() -> None:
    assert _candidate_redirect_rejection("https://arxiv.org/abs/1234.5678", "https://arxiv.org/pdf/1234.5678") is None
    assert _candidate_redirect_rejection("https://example.org/paper", "https://downloads.example.org/paper.pdf") is None
    assert _candidate_redirect_rejection("https://example.org/paper", "https://elsewhere.test/paper.pdf") == "redirect_off_domain"


def test_public_pdf_candidate_decisions_strips_internal_fields() -> None:
    from paperorchestra.reviews.source_support_retrieval import _public_pdf_candidate_decisions

    public = _public_pdf_candidate_decisions(
        [
            {
                "url": "https://example.org/paper.pdf",
                "decision": "accepted",
                "reason": "ok",
                "final_url": "https://example.org/final.pdf",
                "priority": 0,
                "label": "PDF",
            }
        ]
    )

    assert public == [
        {
            "url": "https://example.org/paper.pdf",
            "decision": "accepted",
            "reason": "ok",
            "final_url": "https://example.org/final.pdf",
        }
    ]
