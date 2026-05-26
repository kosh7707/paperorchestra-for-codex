from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main
from paperorchestra.critics import build_citation_support_review, write_citation_support_review
from paperorchestra.models import InputBundle
from paperorchestra.quality_loop_citation_support import _citation_support_check
from paperorchestra.session import artifact_path, create_session, load_session, save_session


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self._body = body
        self.headers = _FakeHeaders({"Content-Type": content_type})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


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
