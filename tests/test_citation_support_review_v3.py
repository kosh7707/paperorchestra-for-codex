from __future__ import annotations

import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main
from paperorchestra.critics import build_citation_support_review, build_source_backed_citation_cases, write_citation_support_review
from paperorchestra.models import InputBundle
from paperorchestra.quality_loop_citation_support import _citation_support_check
from paperorchestra.session import artifact_path, create_session, load_session, save_session


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str, final_url: str | None = None):
        self._body = body
        self.headers = _FakeHeaders({"Content-Type": content_type})
        self._final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def geturl(self) -> str:
        return self._final_url or ""


def _init_source_session(root: Path):
    for name, content in {
        "idea.md": "Synthetic idea.\n",
        "experimental_log.md": "Synthetic log.\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Synthetic guidelines.\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    state = create_session(
        root,
        InputBundle(
            str(root / "idea.md"),
            str(root / "experimental_log.md"),
            str(root / "template.tex"),
            str(root / "guidelines.md"),
            str(root / "figures"),
        ),
    )
    return state


def _request_url(request) -> str:
    return request.full_url if hasattr(request, "full_url") else str(request)


class SourceBackedCitationSupportReviewTests(unittest.TestCase):
    def _setup_single_alpha_url_case(self, root: Path, *, url: str = "https://publisher.example.org/papers/alpha"):
        state = _init_source_session(root)
        paper = artifact_path(root, "paper.full.tex")
        paper.write_text(
            "\\section{Background}\n"
            "Alpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n",
            encoding="utf-8",
        )
        citation_map = artifact_path(root, "citation_map.json")
        citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": url}}), encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.artifacts.citation_map_json = str(citation_map)
        save_session(root, state)
        return state

    def test_source_backed_review_splits_multicite_into_paragraph_cases_and_references_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Related Work}\n"
                "Program-analysis systems increasingly combine graph representations and language models. "
                "Alpha and Beta systems use code graphs to guide vulnerability detection~\\cite{Alpha,Beta}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"},
                        "Beta": {"title": "Beta Code Graph Models", "url": "https://example.test/beta"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha Graph Vulnerability Detection describes using code graphs to guide vulnerability detection.",
                encoding="utf-8",
            )
            artifact_path(root, "references/C2/source.txt").write_text(
                "Beta Code Graph Models also discusses graph representations for vulnerability analysis.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")

        self.assertEqual(review["schema"], "citation-support-review/3")
        self.assertEqual(review["mode"], "source")
        self.assertEqual(review["summary"], {"pass": 2, "weak": 0, "fail": 0, "human_needed": 0})
        self.assertEqual([case["id"] for case in review["cases"]], ["C1", "C2"])
        self.assertEqual([case["key"] for case in review["cases"]], ["Alpha", "Beta"])
        for case in review["cases"]:
            self.assertIn("Program-analysis systems increasingly combine", case["paragraph"])
            self.assertIn("\\cite{Alpha,Beta}", case["anchor"])
            self.assertNotIn("sha256", json.dumps(case).lower())
            self.assertTrue(case["evidence"]["text"].startswith(f"artifacts/references/{case['id']}/"))
            self.assertEqual(case["verdict"], "pass")

    def test_source_type_classifier_does_not_treat_post_quantum_paper_as_blog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Background}\n"
                "Post-quantum authenticated encryption studies evaluate modular hash designs~\\cite{PQPaper}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "PQPaper": {
                            "title": "Synthetic Authenticated Encryption Study",
                            "venue": "Workshop on Post-Quantum Cryptography",
                            "url": "https://publisher.example.org/pqpaper",
                        }
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            cases = build_source_backed_citation_cases(root, resolve_evidence=False)

        self.assertEqual(cases[0]["source"]["type"], "paper")

    def test_source_type_classifier_preserves_doi_less_report_and_source_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Background}\n"
                "Operational reports describe deployment pressure~\\cite{OpsReport}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "OpsReport": {
                            "source_type": "report",
                            "title": "Synthetic Operational Tooling Report",
                            "source_url": "https://publisher.example.org/reports/ops",
                        }
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            cases = build_source_backed_citation_cases(root, resolve_evidence=False)

        self.assertEqual(cases[0]["source"]["type"], "report")
        self.assertEqual(cases[0]["source"]["url"], "https://publisher.example.org/reports/ops")

    def test_source_backed_review_marks_unretrievable_source_as_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nOperational reports show adoption pressure~\\cite{OpsBlog}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"OpsBlog": {"title": "Operational tooling report", "url": "https://example.test/login-only"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(review["summary"], {"pass": 0, "weak": 0, "fail": 0, "human_needed": 1})
        self.assertEqual(case["verdict"], "human_needed")
        self.assertEqual(case["evidence"]["status"], "missing")
        self.assertEqual(case["evidence"]["why"], "unretrieved")
        self.assertIn("artifacts/references/C1/source.pdf", case["ask"])

    def test_source_backed_review_does_not_pass_on_pdf_title_without_readable_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha Graph Vulnerability Detection uses code graphs~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.pdf").write_bytes(b"%PDF-1.4\n")
            with patch("paperorchestra.critics.shutil.which", return_value=None):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertEqual(case["verdict"], "human_needed")
        self.assertIn("source.txt", case["ask"])

    def test_source_backed_review_resolves_arxiv_to_official_pdf_and_writes_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "arxiv": "2401.01234"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                seen_urls.append(_request_url(request))
                return _FakeResponse(b"%PDF-1.4 fake", "application/pdf")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("paperorchestra.critics._extract_pdf_text", side_effect=fake_extract):
                    review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))

        self.assertEqual(seen_urls, ["https://arxiv.org/pdf/2401.01234.pdf"])
        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertTrue(case["evidence"]["path"].endswith("source.pdf"))
        self.assertTrue(case["evidence"]["text"].endswith("source.txt"))
        self.assertEqual(case["verdict"], "pass")
        self.assertEqual(meta["schema"], "citation-source-artifact/1")
        self.assertEqual(meta["case"], "C1")
        self.assertEqual(meta["source"]["arxiv"], "2401.01234")

    def test_source_backed_review_allows_arxiv_abs_landing_to_discover_arxiv_pdf_after_direct_pdf_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "arxiv": "2401.01234"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://arxiv.org/pdf/2401.01234.pdf" and seen_urls.count(url) == 1:
                    raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
                if url == "https://arxiv.org/abs/2401.01234":
                    return _FakeResponse(b'<html><a href="/pdf/2401.01234.pdf">PDF</a></html>', "text/html", final_url=url)
                if url == "https://arxiv.org/pdf/2401.01234.pdf":
                    return _FakeResponse(b"%PDF-1.4 fake", "application/pdf", final_url=url)
                raise AssertionError(f"unexpected URL {url}")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("paperorchestra.critics._extract_pdf_text", side_effect=fake_extract):
                    review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))

        self.assertEqual(
            seen_urls,
            ["https://arxiv.org/pdf/2401.01234.pdf", "https://arxiv.org/abs/2401.01234", "https://arxiv.org/pdf/2401.01234.pdf"],
        )
        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertEqual(case["verdict"], "pass")
        candidates = meta["evidence"]["pdf_candidates"]
        self.assertTrue(any(item["url"] == "https://arxiv.org/pdf/2401.01234.pdf" and item["decision"] == "selected" for item in candidates))

    def test_source_backed_review_resolves_doi_to_official_landing_html_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha reports operational adoption pressure~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Report", "doi": "10.1234/example"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                seen_urls.append(_request_url(request))
                return _FakeResponse(b"<html><body>Alpha reports operational adoption pressure.</body></html>", "text/html")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://doi.org/10.1234/example"])
        self.assertEqual(case["evidence"]["status"], "html")
        self.assertTrue(case["evidence"]["path"].endswith("source.html"))
        self.assertTrue(case["evidence"]["text"].endswith("source.txt"))
        self.assertEqual(case["verdict"], "pass")

    def test_source_backed_review_follows_doi_final_publisher_pdf_before_html_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "doi": "10.1234/official-pdf"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://doi.org/10.1234/official-pdf":
                    return _FakeResponse(
                        b'<html><body><a href="/papers/alpha.pdf">PDF</a> Landing metadata only.</body></html>',
                        "text/html",
                        final_url="https://publisher.example.org/papers/alpha",
                    )
                if url == "https://publisher.example.org/papers/alpha.pdf":
                    return _FakeResponse(b"%PDF-1.4 fake", "application/pdf", final_url=url)
                raise AssertionError(f"unexpected URL {url}")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("paperorchestra.critics._extract_pdf_text", side_effect=fake_extract):
                    review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()

        self.assertEqual(seen_urls, ["https://doi.org/10.1234/official-pdf", "https://publisher.example.org/papers/alpha.pdf"])
        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertTrue(case["evidence"]["path"].endswith("source.pdf"))
        self.assertTrue(case["evidence"]["text"].endswith("source.txt"))
        self.assertEqual(case["evidence"]["url"], "https://publisher.example.org/papers/alpha.pdf")
        self.assertEqual(case["verdict"], "pass")
        self.assertEqual(meta["evidence"]["url"], "https://publisher.example.org/papers/alpha.pdf")
        self.assertFalse(source_html_exists)

    def test_source_backed_review_resolves_official_relative_landing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": "https://publisher.example.org/papers/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://publisher.example.org/papers/alpha":
                    return _FakeResponse(b'<html><a href="/papers/alpha.pdf">Download PDF</a></html>', "text/html", final_url=url)
                if url == "https://publisher.example.org/papers/alpha.pdf":
                    return _FakeResponse(b"%PDF-1.4 fake", "application/pdf", final_url=url)
                raise AssertionError(f"unexpected URL {url}")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("paperorchestra.critics._extract_pdf_text", side_effect=fake_extract):
                    review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://publisher.example.org/papers/alpha", "https://publisher.example.org/papers/alpha.pdf"])
        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertEqual(case["evidence"]["path"], "artifacts/references/C1/source.pdf")
        self.assertEqual(case["evidence"]["text"], "artifacts/references/C1/source.txt")
        self.assertEqual(case["verdict"], "pass")

    def test_source_backed_review_rejects_off_domain_pdf_candidates_with_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": "https://publisher.example.org/papers/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://publisher.example.org/papers/alpha":
                    return _FakeResponse(
                        b'<html><body>Landing only <a href="https://static.example.org/alpha.pdf">same suffix other host</a>'
                        b'<a href="https://mirror.example.net/alpha.pdf">mirror</a>'
                        b'<a href="https://sci-hub.example/alpha.pdf">sci-hub</a></body></html>',
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"unexpected URL {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, ["https://publisher.example.org/papers/alpha"])
        self.assertNotEqual(case["evidence"]["status"], "pdf")
        self.assertIn(case["verdict"], {"weak", "human_needed"})
        self.assertNotEqual(case["verdict"], "pass")
        candidates = meta["evidence"]["pdf_candidates"]
        self.assertTrue(any(item["url"] == "https://static.example.org/alpha.pdf" and item["decision"] == "rejected" for item in candidates))
        self.assertTrue(any(item["url"] == "https://mirror.example.net/alpha.pdf" and item["decision"] == "rejected" for item in candidates))
        self.assertTrue(any(item["url"] == "https://sci-hub.example/alpha.pdf" and item["decision"] == "rejected" for item in candidates))
        self.assertTrue({item["reason"] for item in candidates}.issubset({"off_domain", "disallowed_host"}))
        self.assertFalse(source_pdf_exists)

    def test_source_backed_review_prefers_canonical_pdf_candidate_and_records_deprioritized_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": "https://publisher.example.org/papers/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://publisher.example.org/papers/alpha":
                    return _FakeResponse(
                        b'<html><a href="/papers/alpha-supplement.pdf">Supplement PDF</a>'
                        b'<a href="/papers/alpha.pdf">PDF</a></html>',
                        "text/html",
                        final_url=url,
                    )
                if url == "https://publisher.example.org/papers/alpha.pdf":
                    return _FakeResponse(b"%PDF-1.4 fake", "application/pdf", final_url=url)
                if url == "https://publisher.example.org/papers/alpha-supplement.pdf":
                    return _FakeResponse(b"%PDF-1.4 supplement", "application/pdf", final_url=url)
                raise AssertionError(f"unexpected URL {url}")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("paperorchestra.critics._extract_pdf_text", side_effect=fake_extract):
                    review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))

        self.assertEqual(seen_urls, ["https://publisher.example.org/papers/alpha", "https://publisher.example.org/papers/alpha.pdf"])
        self.assertEqual(case["evidence"]["status"], "pdf")
        self.assertEqual(case["verdict"], "pass")
        candidates = meta["evidence"]["pdf_candidates"]
        self.assertTrue(any(item["url"] == "https://publisher.example.org/papers/alpha.pdf" and item["decision"] == "selected" for item in candidates))
        self.assertTrue(
            any(
                item["url"] == "https://publisher.example.org/papers/alpha-supplement.pdf"
                and item["reason"] == "lower_priority_pdf_candidate"
                for item in candidates
            )
        )

    def test_source_backed_review_rejects_pdf_candidate_redirect_to_off_domain_before_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": "https://publisher.example.org/papers/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://publisher.example.org/papers/alpha":
                    return _FakeResponse(b'<html><a href="/papers/alpha.pdf">PDF</a> Landing only.</html>', "text/html", final_url=url)
                if url == "https://publisher.example.org/papers/alpha.pdf":
                    return _FakeResponse(b"%PDF-1.4 fake", "application/pdf", final_url="https://mirror.example.net/alpha.pdf")
                raise AssertionError(f"unexpected URL {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, ["https://publisher.example.org/papers/alpha", "https://publisher.example.org/papers/alpha.pdf"])
        self.assertFalse(source_pdf_exists)
        self.assertNotEqual(case["evidence"]["status"], "pdf")
        self.assertIn(case["verdict"], {"weak", "human_needed"})
        self.assertNotEqual(case["verdict"], "pass")
        candidates = meta["evidence"]["pdf_candidates"]
        self.assertTrue(
            any(
                item["url"] == "https://publisher.example.org/papers/alpha.pdf"
                and item.get("final_url") == "https://mirror.example.net/alpha.pdf"
                and item["decision"] == "rejected"
                and item["reason"] in {"redirect_off_domain", "disallowed_host"}
                for item in candidates
            )
        )

    def test_source_backed_review_keeps_forbidden_source_blocked_without_mirror_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://publisher.example.org/papers/alpha"])
        self.assertEqual(case["evidence"]["status"], "blocked")
        self.assertEqual(case["evidence"]["why"], "forbidden")
        self.assertEqual(case["verdict"], "human_needed")
        self.assertIn("artifacts/references/C1/source.pdf", case["ask"])

    def test_source_backed_review_blocks_login_html_without_fetching_pdf_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            landing_url = "https://publisher.example.org/papers/alpha"
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == landing_url:
                    return _FakeResponse(
                        b"<html><body>Sign in to access this article."
                        b"<input type=\"password\" name=\"password\">"
                        b"<a href=\"/papers/alpha.pdf\">PDF</a></body></html>",
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"blocked landing page must not fetch PDF candidate {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            meta = json.loads(artifact_path(root, "references/C1/source.meta.json").read_text(encoding="utf-8"))
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()
            source_txt_exists = artifact_path(root, "references/C1/source.txt").exists()
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, [landing_url])
        self.assertEqual(case["evidence"], {"status": "blocked", "why": "login_required", "url": landing_url})
        self.assertEqual(case["verdict"], "human_needed")
        self.assertIn("login_required", case["ask"])
        self.assertIn("artifacts/references/C1/source.pdf", case["ask"])
        self.assertEqual(meta["evidence"]["why"], "login_required")
        self.assertFalse(source_html_exists)
        self.assertFalse(source_txt_exists)
        self.assertFalse(source_pdf_exists)

    def test_source_backed_review_blocks_captcha_html_before_pdf_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            landing_url = "https://publisher.example.org/papers/alpha"
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == landing_url:
                    return _FakeResponse(
                        b"<html><body>reCAPTCHA challenge: verify you are human."
                        b"Sign in to access this article."
                        b"<a href=\"/papers/alpha.pdf\">PDF</a></body></html>",
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"blocked landing page must not fetch PDF candidate {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()
            source_txt_exists = artifact_path(root, "references/C1/source.txt").exists()
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, [landing_url])
        self.assertEqual(case["evidence"]["status"], "blocked")
        self.assertEqual(case["evidence"]["why"], "captcha")
        self.assertEqual(case["verdict"], "human_needed")
        self.assertFalse(source_html_exists)
        self.assertFalse(source_txt_exists)
        self.assertFalse(source_pdf_exists)

    def test_source_backed_review_blocks_paywall_html_without_passing_on_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            landing_url = "https://publisher.example.org/papers/alpha"
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == landing_url:
                    return _FakeResponse(
                        b"<html><body>Alpha uses code graphs for vulnerability detection. "
                        b"Purchase access for the full text article. Institutional access options are available. "
                        b"<a href=\"/papers/alpha.pdf\">PDF</a></body></html>",
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"blocked landing page must not fetch PDF candidate {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()
            source_txt_exists = artifact_path(root, "references/C1/source.txt").exists()
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, [landing_url])
        self.assertEqual(case["evidence"]["status"], "blocked")
        self.assertEqual(case["evidence"]["why"], "paywall")
        self.assertEqual(case["verdict"], "human_needed")
        self.assertFalse(source_html_exists)
        self.assertFalse(source_txt_exists)
        self.assertFalse(source_pdf_exists)

    def test_source_backed_review_blocks_generic_antibot_html_as_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            landing_url = "https://publisher.example.org/papers/alpha"
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == landing_url:
                    return _FakeResponse(
                        b"<html><body>Access denied. Request blocked due to automated traffic. "
                        b"<a href=\"/papers/alpha.pdf\">PDF</a></body></html>",
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"blocked landing page must not fetch PDF candidate {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()
            source_txt_exists = artifact_path(root, "references/C1/source.txt").exists()
            source_pdf_exists = artifact_path(root, "references/C1/source.pdf").exists()

        self.assertEqual(seen_urls, [landing_url])
        self.assertEqual(case["evidence"]["status"], "blocked")
        self.assertEqual(case["evidence"]["why"], "forbidden")
        self.assertEqual(case["verdict"], "human_needed")
        self.assertFalse(source_html_exists)
        self.assertFalse(source_txt_exists)
        self.assertFalse(source_pdf_exists)

    def test_source_backed_review_keeps_normal_html_with_benign_login_words_passable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            landing_url = "https://publisher.example.org/papers/alpha"
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == landing_url:
                    return _FakeResponse(
                        b"<html><body>Alpha uses code graphs for vulnerability detection. "
                        b"The study discusses a subscription model for tool deployment and a login experiment benchmark, "
                        b"but this article body is fully readable.</body></html>",
                        "text/html",
                        final_url=url,
                    )
                raise AssertionError(f"unexpected URL {url}")

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            source_html_exists = artifact_path(root, "references/C1/source.html").exists()
            source_txt_exists = artifact_path(root, "references/C1/source.txt").exists()

        self.assertEqual(seen_urls, [landing_url])
        self.assertEqual(case["evidence"]["status"], "html")
        self.assertEqual(case["evidence"]["path"], "artifacts/references/C1/source.html")
        self.assertEqual(case["evidence"]["text"], "artifacts/references/C1/source.txt")
        self.assertEqual(case["verdict"], "pass")
        self.assertTrue(source_html_exists)
        self.assertTrue(source_txt_exists)

    def test_source_inspector_does_not_pass_diffuse_keyword_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha is the name of a research prototype. "
                "Separately, code graphs appear in program analysis. "
                "Vulnerability detection remains difficult in deployment.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "weak")
        self.assertLess(len(case["note"]), 180)
        self.assertNotIn("Vulnerability detection remains difficult", case["note"])

    def test_source_inspector_requires_subject_entity_for_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Code graphs support vulnerability detection in several production systems.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "weak")
        self.assertEqual(review["summary"], {"pass": 0, "weak": 1, "fail": 0, "human_needed": 0})

    def test_source_inspector_marks_weaker_general_support_as_weak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha explores code graphs for program analysis and visualization.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "weak")
        self.assertEqual(review["summary"], {"pass": 0, "weak": 1, "fail": 0, "human_needed": 0})

    def test_source_inspector_keeps_direct_support_as_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection in deployed analysis workflows.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "pass")
        self.assertEqual(review["summary"], {"pass": 1, "weak": 0, "fail": 0, "human_needed": 0})

    def test_source_inspector_marks_direct_contradiction_as_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha does not use code graphs for vulnerability detection.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "fail")
        self.assertEqual(review["summary"], {"pass": 0, "weak": 0, "fail": 1, "human_needed": 0})

    def test_source_inspector_does_not_fail_benign_or_unrelated_negation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha not only uses code graphs for vulnerability detection, it also reports triage outcomes. "
                "A separate baseline is not evaluated in this artifact.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "pass")
        self.assertNotEqual(case["verdict"], "fail")

    def test_source_inspector_later_contradiction_overrides_earlier_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection in an early prototype. "
                "However, the final evaluated Alpha system does not use code graphs for vulnerability detection.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "fail")
        self.assertEqual(review["summary"], {"pass": 0, "weak": 0, "fail": 1, "human_needed": 0})

    def test_source_inspector_ignores_poisoned_non_target_context_and_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Background}\n"
                "Alpha uses code graphs for vulnerability detection. "
                "Alpha improves triage~\\cite{Alpha}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(str(case["target"]).strip(), "Alpha improves triage")
        self.assertNotEqual(case["verdict"], "pass")

    def test_source_inspector_keeps_citation_cases_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text(
                "\\section{Background}\n"
                "Alpha improves triage~\\cite{Alpha}. "
                "Beta uses code graphs for vulnerability detection~\\cite{Beta}.\n",
                encoding="utf-8",
            )
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"},
                        "Beta": {"title": "Beta Graph Vulnerability Detection", "url": "https://example.test/beta"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha is a prototype.", encoding="utf-8")
            artifact_path(root, "references/C2/source.txt").write_text(
                "Beta uses code graphs for vulnerability detection.",
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            by_key = {case["key"]: case for case in review["cases"]}

        self.assertNotEqual(by_key["Alpha"]["verdict"], "pass")
        self.assertEqual(by_key["Beta"]["verdict"], "pass")

    def test_write_source_backed_review_emits_short_human_needed_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nOperational reports show adoption pressure~\\cite{OpsBlog}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"OpsBlog": {"title": "Operational tooling report", "url": "https://example.test/login-only"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)

            review_path = write_citation_support_review(root, evidence_mode="source")
            markdown_path = review_path.with_name("citation_support_human_needed.md")
            markdown_exists = markdown_path.exists()
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertTrue(markdown_exists)
        self.assertIn("Citation source follow-up", markdown)
        self.assertIn("OpsBlog", markdown)
        self.assertIn("artifacts/references/C1/source.pdf", markdown)
        self.assertIn("Paragraph:", markdown)
        self.assertIn("Anchor:", markdown)
        self.assertIn("Operational reports show adoption pressure", markdown)
        self.assertNotIn('"cases"', markdown)
        self.assertLess(len(markdown), 1800)

    def test_write_source_backed_review_removes_stale_human_needed_markdown_after_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            review_path = write_citation_support_review(root, evidence_mode="source")
            markdown_path = review_path.with_name("citation_support_human_needed.md")
            self.assertTrue(markdown_path.exists())

            artifact_path(root, "references/C1/source.txt").write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
            write_citation_support_review(root, evidence_mode="source")
            stale_removed = not markdown_path.exists()

        self.assertTrue(stale_removed)

    def test_human_resolution_source_url_ignores_stale_source_and_reinspects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root, url="https://example.test/stale")
            stale = artifact_path(root, "references/C1/source.txt")
            stale.write_text("Alpha is only a prototype with no graph evidence.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "provide_source_url",
                        "url": "https://publisher.example.org/alpha-source",
                    }
                ),
                encoding="utf-8",
            )
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                return _FakeResponse(
                    b"<html><body>Alpha uses code graphs for vulnerability detection.</body></html>",
                    "text/html",
                    final_url=url,
                )

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://publisher.example.org/alpha-source"])
        self.assertEqual(case["source"]["url"], "https://publisher.example.org/alpha-source")
        self.assertEqual(case["resolution"]["action"], "provide_source_url")
        self.assertEqual(case["resolution"]["status"], "applied")
        self.assertEqual(case["verdict"], "pass")

    def test_human_resolution_source_url_unsupported_fetch_does_not_auto_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root, url="https://example.test/stale")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "provide_source_url",
                        "url": "https://publisher.example.org/alpha-source",
                    }
                ),
                encoding="utf-8",
            )

            def fake_urlopen(request, timeout=10):
                return _FakeResponse(
                    b"<html><body>Alpha is a prototype dashboard.</body></html>",
                    "text/html",
                    final_url=_request_url(request),
                )

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertIn("resolution", case)
        self.assertEqual(case["resolution"]["action"], "provide_source_url")
        self.assertNotEqual(case["verdict"], "pass")

    def test_human_resolution_source_url_overrides_stale_arxiv_locator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps({"Alpha": {"title": "Old Alpha", "arxiv": "2401.99999", "url": "https://example.test/stale"}}),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "provide_source_url",
                        "url": "https://publisher.example.org/human-alpha",
                    }
                ),
                encoding="utf-8",
            )
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                return _FakeResponse(
                    b"<html><body>Alpha uses code graphs for vulnerability detection.</body></html>",
                    "text/html",
                    final_url=url,
                )

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://publisher.example.org/human-alpha"])
        self.assertNotIn("arxiv", case["source"])
        self.assertEqual(case["verdict"], "pass")

    def test_human_resolution_replacement_citation_revalidates_replacement_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "Alpha": {"title": "Unsupported Alpha", "url": "https://example.test/old-alpha"},
                        "Better": {"title": "Better Graph Study", "url": "https://publisher.example.org/better"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha is unrelated to graph-based vulnerability detection.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "replace_citation",
                        "replacement_key": "Better",
                    }
                ),
                encoding="utf-8",
            )
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                return _FakeResponse(
                    b"<html><body>Better shows Alpha uses code graphs for vulnerability detection.</body></html>",
                    "text/html",
                    final_url=url,
                )

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(seen_urls, ["https://publisher.example.org/better"])
        self.assertEqual(case["key"], "Better")
        self.assertEqual(case["resolution"]["action"], "replace_citation")
        self.assertEqual(case["resolution"]["original_key"], "Alpha")
        self.assertEqual(case["resolution"]["replacement_key"], "Better")
        self.assertEqual(case["verdict"], "pass")

    def test_human_resolution_replacement_unsupported_source_does_not_auto_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "Alpha": {"title": "Unsupported Alpha", "url": "https://example.test/old-alpha"},
                        "Better": {"title": "Better Graph Study", "url": "https://publisher.example.org/better"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "replace_citation",
                        "replacement_key": "Better",
                    }
                ),
                encoding="utf-8",
            )

            def fake_urlopen(request, timeout=10):
                return _FakeResponse(
                    b"<html><body>Better studies unrelated dashboards.</body></html>",
                    "text/html",
                    final_url=_request_url(request),
                )

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen):
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["key"], "Better")
        self.assertIn("resolution", case)
        self.assertEqual(case["resolution"]["action"], "replace_citation")
        self.assertNotEqual(case["verdict"], "pass")

    def test_human_resolution_replacement_uses_operator_supplied_source_artifact_when_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(
                json.dumps(
                    {
                        "Alpha": {"title": "Unsupported Alpha", "url": "https://example.test/old-alpha"},
                        "Better": {"title": "Better Graph Study", "url": "https://publisher.example.org/better"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text("Better shows Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "replace_citation",
                        "replacement_key": "Better",
                        "use_provided_source": True,
                    }
                ),
                encoding="utf-8",
            )

            with patch("paperorchestra.critics.urllib.request.urlopen") as urlopen:
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        urlopen.assert_not_called()
        self.assertEqual(case["key"], "Better")
        self.assertEqual(case["evidence"]["status"], "text")
        self.assertEqual(case["resolution"]["source"], "provided")
        self.assertEqual(case["verdict"], "pass")

    def test_human_resolution_weaken_claim_changes_target_but_requires_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha uses code graphs.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "weaken_claim",
                        "target": "Alpha uses code graphs",
                    }
                ),
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["target"], "Alpha uses code graphs")
        self.assertEqual(case["resolution"]["action"], "weaken_claim")
        self.assertIn("vulnerability detection", case["resolution"]["original_target"])
        self.assertEqual(case["resolution"]["target"], "Alpha uses code graphs")
        self.assertEqual(case["verdict"], "pass")

    def test_human_resolution_weaken_claim_without_source_support_does_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha is a prototype dashboard.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "weaken_claim",
                        "target": "Alpha uses code graphs",
                    }
                ),
                encoding="utf-8",
            )

            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertIn("resolution", case)
        self.assertEqual(case["resolution"]["action"], "weaken_claim")
        self.assertEqual(case["target"], "Alpha uses code graphs")
        self.assertNotEqual(case["verdict"], "pass")

    def test_human_resolution_remove_claim_is_audited_but_not_source_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_single_alpha_url_case(root)
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "remove_claim",
                        "reason": "The claim is unsupported by available sources.",
                    }
                ),
                encoding="utf-8",
            )

            with patch(
                "paperorchestra.critics.urllib.request.urlopen",
                return_value=_FakeResponse(b"<html><body>Network should not be consulted for removal.</body></html>", "text/html"),
            ) as urlopen:
                review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]

        self.assertEqual(case["verdict"], "human_needed")
        self.assertIn("resolution", case)
        self.assertEqual(case["resolution"]["action"], "remove_claim")
        self.assertEqual(case["resolution"]["status"], "requires_manuscript_edit")
        self.assertIn("remove", case["ask"].lower())
        self.assertNotIn(case["verdict"], {"pass", "weak"})
        urlopen.assert_not_called()

    def test_debug_citation_sources_cli_resolves_sources_without_support_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph", "url": "https://example.test/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            source_text = artifact_path(root, "references/C1/source.txt")
            source_text.write_text("Alpha uses code graphs.", encoding="utf-8")
            output = root / "retrieval-debug.json"

            with patch("os.getcwd", return_value=str(root)):
                code = cli_main(["debug-citation-sources", "--output", str(output)])
            payload = json.loads(output.read_text(encoding="utf-8"))
            support_review_exists = artifact_path(root, "citation_support_review.json").exists()

        self.assertEqual(code, 0)
        self.assertFalse(support_review_exists)
        self.assertEqual(payload["schema"], "citation-source-retrieval-debug/1")
        self.assertEqual(payload["summary"], {"text": 1})
        self.assertEqual(payload["items"][0]["evidence"]["text"], "artifacts/references/C1/source.txt")

    def test_claim_safe_support_check_accepts_source_backed_v3_and_fails_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs~\\cite{Alpha}.\n", encoding="utf-8")
            citation_map = artifact_path(root, "citation_map.json")
            citation_map.write_text(json.dumps({"Alpha": {"title": "Alpha Graph Vulnerability Detection", "url": "https://example.test/alpha"}}), encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.citation_map_json = str(citation_map)
            save_session(root, state)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
            review = build_citation_support_review(root, evidence_mode="source")
            artifact_path(root, "citation_support_review.json").write_text(json.dumps(review), encoding="utf-8")

            check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["canonical_summary"], {"pass": 1, "weak": 0, "fail": 0, "human_needed": 0})


    def test_claim_safe_support_check_rejects_v3_when_citation_target_context_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._setup_single_alpha_url_case(root)
            paper = Path(state.artifacts.paper_full_tex)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection.", encoding="utf-8"
            )
            review = build_citation_support_review(root, evidence_mode="source")
            artifact_path(root, "citation_support_review.json").write_text(json.dumps(review), encoding="utf-8")

            paper.write_text(
                "\\section{Background}\n"
                "Alpha eliminates all false positives in production scanners~\\cite{Alpha}.\n",
                encoding="utf-8",
            )
            with patch("paperorchestra.critics.urllib.request.urlopen") as urlopen:
                check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        urlopen.assert_not_called()
        self.assertEqual(check["status"], "fail")
        self.assertIn("citation_support_case_context_mismatch", check["failing_codes"])
        self.assertEqual(check["context_mismatch_count"], 1)
        self.assertEqual(check["context_mismatch_indexes"], [0])
        self.assertEqual(check["review_case_context_count"], 1)
        self.assertEqual(check["current_case_context_count"], 1)

    def test_claim_safe_support_check_allows_v3_when_only_uncited_text_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._setup_single_alpha_url_case(root)
            paper = Path(state.artifacts.paper_full_tex)
            original_text = paper.read_text(encoding="utf-8")
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection.", encoding="utf-8"
            )
            review = build_citation_support_review(root, evidence_mode="source")
            artifact_path(root, "citation_support_review.json").write_text(json.dumps(review), encoding="utf-8")

            paper.write_text(original_text + "\n\nThis uncited operational note should not stale citation case context.\n", encoding="utf-8")
            with patch("paperorchestra.critics.urllib.request.urlopen") as urlopen:
                check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        urlopen.assert_not_called()
        self.assertEqual(check["status"], "pass")
        self.assertNotIn("citation_support_case_context_mismatch", check["failing_codes"])
        self.assertEqual(check["context_mismatch_count"], 0)
        self.assertEqual(check["context_mismatch_indexes"], [])
        self.assertEqual(check["review_case_context_count"], 1)
        self.assertEqual(check["current_case_context_count"], 1)

    def test_claim_safe_support_check_rejects_v3_when_citation_location_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._setup_single_alpha_url_case(root)
            paper = Path(state.artifacts.paper_full_tex)
            artifact_path(root, "references/C1/source.txt").write_text(
                "Alpha uses code graphs for vulnerability detection.", encoding="utf-8"
            )
            review = build_citation_support_review(root, evidence_mode="source")
            artifact_path(root, "citation_support_review.json").write_text(json.dumps(review), encoding="utf-8")

            paper.write_text(
                "\\section{Related Work}\n"
                "Alpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n",
                encoding="utf-8",
            )
            with patch("paperorchestra.critics.urllib.request.urlopen") as urlopen:
                check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        urlopen.assert_not_called()
        self.assertEqual(check["status"], "fail")
        self.assertIn("citation_support_case_context_mismatch", check["failing_codes"])
        self.assertEqual(check["context_mismatch_count"], 1)
        self.assertEqual(check["context_mismatch_indexes"], [0])
        self.assertEqual(check["review_case_context_count"], 1)
        self.assertEqual(check["current_case_context_count"], 1)

    def test_claim_safe_support_check_uses_original_target_for_weaken_claim_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._setup_single_alpha_url_case(root)
            paper = Path(state.artifacts.paper_full_tex)
            artifact_path(root, "references/C1/source.txt").write_text("Alpha uses code graphs.", encoding="utf-8")
            artifact_path(root, "references/C1/human-resolution.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-human-resolution/1",
                        "case": "C1",
                        "action": "weaken_claim",
                        "target": "Alpha uses code graphs",
                    }
                ),
                encoding="utf-8",
            )
            review = build_citation_support_review(root, evidence_mode="source")
            case = review["cases"][0]
            self.assertEqual(case["target"], "Alpha uses code graphs")
            self.assertEqual(case["resolution"]["action"], "weaken_claim")
            self.assertIn("vulnerability detection", case["resolution"]["original_target"])
            artifact_path(root, "citation_support_review.json").write_text(json.dumps(review), encoding="utf-8")

            with patch("paperorchestra.critics.urllib.request.urlopen") as unchanged_urlopen:
                unchanged_check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")
            paper.write_text(
                "\\section{Background}\n"
                "Alpha eliminates all false positives in production scanners~\\cite{Alpha}.\n",
                encoding="utf-8",
            )
            with patch("paperorchestra.critics.urllib.request.urlopen") as changed_urlopen:
                changed_check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        unchanged_urlopen.assert_not_called()
        changed_urlopen.assert_not_called()
        self.assertEqual(unchanged_check["status"], "pass")
        self.assertEqual(unchanged_check["context_mismatch_count"], 0)
        self.assertEqual(unchanged_check["context_mismatch_indexes"], [])
        self.assertEqual(unchanged_check["review_case_context_count"], 1)
        self.assertEqual(unchanged_check["current_case_context_count"], 1)
        self.assertEqual(changed_check["status"], "fail")
        self.assertIn("citation_support_case_context_mismatch", changed_check["failing_codes"])
        self.assertEqual(changed_check["context_mismatch_count"], 1)
        self.assertEqual(changed_check["context_mismatch_indexes"], [0])
        self.assertEqual(changed_check["review_case_context_count"], 1)
        self.assertEqual(changed_check["current_case_context_count"], 1)

    def test_claim_safe_support_check_rejects_pass_without_readable_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = _init_source_session(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\section{Background}\nAlpha uses code graphs~\\cite{Alpha}.\n", encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            save_session(root, state)
            artifact_path(root, "citation_support_review.json").write_text(
                json.dumps(
                    {
                        "schema": "citation-support-review/3",
                        "mode": "source",
                        "summary": {"pass": 1, "weak": 0, "fail": 0, "human_needed": 0},
                        "cases": [
                            {
                                "id": "C1",
                                "key": "Alpha",
                                "loc": "Background ¶1",
                                "paragraph": "Alpha uses code graphs~\\cite{Alpha}.",
                                "anchor": "Alpha uses code graphs~\\cite{Alpha}.",
                                "target": "Alpha uses code graphs",
                                "source": {"type": "paper", "title": "Alpha Graph Vulnerability Detection"},
                                "evidence": {"status": "pdf", "path": "artifacts/references/C1/source.pdf"},
                                "verdict": "pass",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifact_path(root, "references/C1/source.pdf").write_bytes(b"%PDF-1.4\n")

            check = _citation_support_check(root, load_session(root), quality_mode="claim_safe")

        self.assertEqual(check["status"], "fail")
        self.assertIn("citation_support_evidence_missing", check["failing_codes"])
