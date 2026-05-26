from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra import orchestra_citation_quality as ocq
from paperorchestra.citation_integrity import rendered_reference_audit_path, write_rendered_reference_audit
from paperorchestra.critics import build_citation_support_review
from paperorchestra.models import InputBundle
from paperorchestra.session import artifact_path, create_session, load_session, save_session


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


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


def _request_url(request) -> str:
    return request.full_url if hasattr(request, "full_url") else str(request)


def _init_session(root: Path, *, paper_text: str, citation_map: dict[str, dict], bbl_keys: list[str] | None = None):
    for name, content in {
        "idea.md": "Synthetic citation smoke idea.\n",
        "experimental_log.md": "Synthetic citation smoke log.\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Synthetic citation smoke guidelines.\n",
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
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text(paper_text, encoding="utf-8")
    citation_map_path = artifact_path(root, "citation_map.json")
    citation_map_path.write_text(json.dumps(citation_map), encoding="utf-8")
    references = artifact_path(root, "references.bib")
    bib_entries = []
    for key, value in citation_map.items():
        fields = [
            f"  title = {{{value.get('title', key + ' Title')}}}",
            "  author = {Ada Example}",
            "  year = {2026}",
            f"  journal = {{{value.get('journal', 'Synthetic Smoke Venue')}}}",
        ]
        if value.get("url"):
            fields.append(f"  url = {{{value['url']}}}")
        if value.get("doi"):
            fields.append(f"  doi = {{{value['doi']}}}")
        bib_entries.append(f"@article{{{key},\n" + ",\n".join(fields) + "\n}")
    references.write_text("\n\n".join(bib_entries) + "\n", encoding="utf-8")
    bbl = artifact_path(root, "paper.full.bbl")
    bbl.write_text("\n".join(f"\\bibitem{{{key}}} Rendered {key}." for key in (bbl_keys or list(citation_map))) + "\n", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.artifacts.references_bib = str(references)
    save_session(root, state)
    return load_session(root)


def _write_claim_map(root: Path, claims: list[dict]) -> None:
    path = artifact_path(root, "claim_map.json")
    path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    state = load_session(root)
    state.artifacts.claim_map_json = str(path)
    save_session(root, state)


def _write_v2_support_review(root: Path, items: list[dict]) -> None:
    state = load_session(root)
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    path.write_text(json.dumps({"items": items, "evidence_mode": "web"}), encoding="utf-8")


def _write_v3_support_review(root: Path, cases: list[dict]) -> None:
    state = load_session(root)
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    summary = {"pass": 0, "weak": 0, "fail": 0, "human_needed": 0}
    for case in cases:
        summary[str(case.get("verdict") or "human_needed")] += 1
    path.write_text(json.dumps({"schema": "citation-support-review/3", "mode": "source", "summary": summary, "cases": cases}), encoding="utf-8")


def _assert_exact_lean_cqg(test: unittest.TestCase, payload: dict) -> None:
    test.assertEqual(set(payload), {"schema", "status", "summary", "failures"})
    test.assertEqual(payload["schema"], "citation-quality-gate/2")
    test.assertIn(payload["status"], {"pass", "warn", "fail"})
    test.assertEqual(set(payload["summary"]), {"pass", "weak", "fail", "human_needed"})
    for failure in payload["failures"]:
        test.assertEqual(set(failure), {"case", "key", "code", "message"})


def _internal_cqg_path(test: unittest.TestCase, root: Path) -> Path:
    func = getattr(ocq, "citation_quality_gate_internal_path", None)
    test.assertIsNotNone(func, "citation_quality_gate_internal_path must exist for the smoke compat artifact")
    return func(root)


class CitationPathSmokeTests(unittest.TestCase):
    def test_smoke_source_review_covers_pdf_html_blocked_and_multicite_in_one_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(
                root,
                paper_text=(
                    "\\section{Background}\n\n"
                    "Alpha uses code graphs for vulnerability detection~\\cite{Alpha}.\n"
                    "Beta reports operational adoption pressure~\\cite{Beta}.\n"
                    "Gamma requires protected portal evidence~\\cite{Gamma}.\n"
                    "Delta and Epsilon use graph cues for vulnerability triage~\\cite{Delta,Epsilon}.\n"
                ),
                citation_map={
                    "Alpha": {"title": "Alpha Graph", "url": "https://publisher.example.org/alpha.pdf"},
                    "Beta": {"title": "Beta Operations", "doi": "10.1234/beta"},
                    "Gamma": {"title": "Gamma Portal", "url": "https://publisher.example.org/gamma"},
                    "Delta": {"title": "Delta Graph Cues", "url": "https://example.test/delta"},
                    "Epsilon": {"title": "Epsilon Triage", "url": "https://example.test/epsilon"},
                },
            )
            artifact_path(root, "references/C4/source.txt").write_text(
                "Delta uses graph cues for vulnerability triage.", encoding="utf-8"
            )
            artifact_path(root, "references/C5/source.txt").write_text(
                "Epsilon uses graph cues for vulnerability triage.", encoding="utf-8"
            )
            seen_urls: list[str] = []

            def fake_urlopen(request, timeout=10):
                url = _request_url(request)
                seen_urls.append(url)
                if url == "https://publisher.example.org/alpha.pdf":
                    return _FakeResponse(b"%PDF-1.4 alpha", "application/pdf", final_url=url)
                if url == "https://doi.org/10.1234/beta":
                    return _FakeResponse(
                        b"<html><body>Beta reports operational adoption pressure.</body></html>",
                        "text/html",
                        final_url="https://publisher.example.org/beta",
                    )
                if url == "https://publisher.example.org/gamma":
                    return _FakeResponse(
                        b"<html><body>Login required to access this paper. <a href='/gamma.pdf'>PDF</a></body></html>",
                        "text/html",
                        final_url=url,
                    )
                if url.endswith("/gamma.pdf"):
                    raise AssertionError("blocked landing page must not fetch PDF candidates")
                raise AssertionError(f"unexpected network access: {url}")

            def fake_extract(pdf_path: Path, text_path: Path) -> bool:
                text_path.write_text("Alpha uses code graphs for vulnerability detection.", encoding="utf-8")
                return True

            with patch("paperorchestra.critics.urllib.request.urlopen", side_effect=fake_urlopen), patch(
                "paperorchestra.critics._extract_pdf_text", side_effect=fake_extract
            ):
                review = build_citation_support_review(root, evidence_mode="source")

        self.assertEqual(review["schema"], "citation-support-review/3")
        self.assertEqual(review["summary"], {"pass": 4, "weak": 0, "fail": 0, "human_needed": 1})
        self.assertEqual([case["key"] for case in review["cases"]], ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"])
        by_key = {case["key"]: case for case in review["cases"]}
        self.assertEqual(by_key["Alpha"]["evidence"]["status"], "pdf")
        self.assertEqual(by_key["Alpha"]["evidence"]["path"], "artifacts/references/C1/source.pdf")
        self.assertEqual(by_key["Alpha"]["evidence"]["text"], "artifacts/references/C1/source.txt")
        self.assertEqual(by_key["Beta"]["evidence"]["status"], "html")
        self.assertEqual(by_key["Beta"]["evidence"]["text"], "artifacts/references/C2/source.txt")
        self.assertEqual(by_key["Gamma"]["verdict"], "human_needed")
        self.assertEqual(by_key["Gamma"]["evidence"], {"status": "blocked", "why": "login_required", "url": "https://publisher.example.org/gamma"})
        self.assertEqual(by_key["Delta"]["id"], "C4")
        self.assertEqual(by_key["Epsilon"]["id"], "C5")
        self.assertEqual(seen_urls, ["https://publisher.example.org/alpha.pdf", "https://doi.org/10.1234/beta", "https://publisher.example.org/gamma"])

    def test_smoke_cqg_writes_lean_public_and_internal_compat_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(
                root,
                paper_text="\\section{Background}\n\nModern needs source support~\\cite{Modern}.\n",
                citation_map={"Modern": {"title": "Modern Source", "url": "https://example.test/modern"}},
            )
            write_rendered_reference_audit(root, quality_mode="claim_safe")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Modern"]}])
            artifact_path(root, "references/C1/source.txt").write_text("Modern needs source support.", encoding="utf-8")
            _write_v3_support_review(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Modern",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_CONTEXT Modern needs source support~\\cite{Modern}.",
                        "anchor": "PRIVATE_ANCHOR Modern needs source support~\\cite{Modern}.",
                        "target": "Modern needs source support",
                        "source": {"type": "paper", "title": "PRIVATE_TITLE"},
                        "evidence": {"status": "text", "text": "artifacts/references/C1/source.txt"},
                        "verdict": "pass",
                    }
                ],
            )

            public_path, returned = ocq.write_citation_quality_gate(root, quality_mode="claim_safe")
            public_payload = json.loads(public_path.read_text(encoding="utf-8"))
            internal_path = _internal_cqg_path(self, root)
            internal_payload = json.loads(internal_path.read_text(encoding="utf-8"))

        for payload in (returned, public_payload):
            _assert_exact_lean_cqg(self, payload)
            rendered = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("PRIVATE_CONTEXT", rendered)
            self.assertNotIn("PRIVATE_ANCHOR", rendered)
            self.assertNotIn("PRIVATE_TITLE", rendered)
            self.assertNotIn("source_artifact_hashes", rendered)
        self.assertEqual(internal_payload["schema_version"], "citation-quality-gate/2")
        self.assertEqual(internal_payload["public_report"], public_payload)
        self.assertIn("items", internal_payload)
        self.assertIn("counts", internal_payload)
        self.assertIn("hard_gate_failures", internal_payload)
        self.assertIn("source_artifact_hashes", internal_payload)

    def test_smoke_cqg_supports_legacy_v2_and_v3_reviews_without_bloating_public_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            legacy_root = Path(tmp) / "legacy"
            legacy_root.mkdir()
            _init_session(
                legacy_root,
                paper_text="\\section{Background}\n\nLegacy is supported~\\cite{Legacy}.\n",
                citation_map={"Legacy": {"title": "Legacy Source", "url": "https://example.test/legacy"}},
            )
            write_rendered_reference_audit(legacy_root, quality_mode="claim_safe")
            artifact_path(legacy_root, "references/C1/source.txt").write_text("Legacy is supported.", encoding="utf-8")
            _write_v2_support_review(
                legacy_root,
                [{"id": "support-1", "sentence": "Legacy is supported~\\cite{Legacy}.", "citation_keys": ["Legacy"], "support_status": "supported", "critical": True}],
            )
            legacy_public_path, legacy_returned = ocq.write_citation_quality_gate(legacy_root, quality_mode="claim_safe")
            legacy_written = json.loads(legacy_public_path.read_text(encoding="utf-8"))
            legacy_internal = json.loads(_internal_cqg_path(self, legacy_root).read_text(encoding="utf-8"))

            modern_root = Path(tmp) / "modern"
            modern_root.mkdir()
            _init_session(
                modern_root,
                paper_text="\\section{Background}\n\nModern is supported~\\cite{Modern}.\n",
                citation_map={"Modern": {"title": "Modern Source", "url": "https://example.test/modern"}},
            )
            write_rendered_reference_audit(modern_root, quality_mode="claim_safe")
            _write_claim_map(modern_root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Modern"]}])
            artifact_path(modern_root, "references/C1/source.txt").write_text("Modern is supported.", encoding="utf-8")
            _write_v3_support_review(
                modern_root,
                [{"id": "C1", "key": "Modern", "evidence": {"status": "text", "text": "artifacts/references/C1/source.txt"}, "verdict": "pass"}],
            )
            modern_public_path, modern_returned = ocq.write_citation_quality_gate(modern_root, quality_mode="claim_safe")
            modern_written = json.loads(modern_public_path.read_text(encoding="utf-8"))
            modern_internal = json.loads(_internal_cqg_path(self, modern_root).read_text(encoding="utf-8"))

            missing_text_root = Path(tmp) / "missing-text"
            missing_text_root.mkdir()
            _init_session(
                missing_text_root,
                paper_text="\\section{Background}\n\nModern requires readable source text~\\cite{Modern}.\n",
                citation_map={"Modern": {"title": "Modern Source", "url": "https://example.test/modern"}},
            )
            write_rendered_reference_audit(missing_text_root, quality_mode="claim_safe")
            _write_claim_map(missing_text_root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Modern"]}])
            artifact_path(missing_text_root, "references/C1/source.pdf").write_bytes(b"%PDF-1.4\n")
            _write_v3_support_review(
                missing_text_root,
                [{"id": "C1", "key": "Modern", "evidence": {"status": "pdf", "path": "artifacts/references/C1/source.pdf"}, "verdict": "pass"}],
            )
            missing_public_path, missing_returned = ocq.write_citation_quality_gate(missing_text_root, quality_mode="claim_safe")
            missing_written = json.loads(missing_public_path.read_text(encoding="utf-8"))
            missing_internal = json.loads(_internal_cqg_path(self, missing_text_root).read_text(encoding="utf-8"))

        for returned, written in ((legacy_returned, legacy_written), (modern_returned, modern_written), (missing_returned, missing_written)):
            _assert_exact_lean_cqg(self, returned)
            _assert_exact_lean_cqg(self, written)
        self.assertEqual(legacy_returned["summary"]["pass"], 1)
        self.assertTrue(
            any(item.get("support_status") == "supported" and item.get("critical") is True for item in legacy_internal["items"]),
            "legacy v2 supported critical item must be consumed into the internal CQG items",
        )
        self.assertGreaterEqual(len(modern_internal["items"]), 1)
        self.assertIn("counts", legacy_internal)
        self.assertIn("counts", modern_internal)
        self.assertEqual(modern_internal["hard_gate_failures"], [])
        self.assertIn("critical_unsupported_citation", missing_internal["hard_gate_failures"])
        self.assertEqual(missing_returned["status"], "fail")

    def test_smoke_cqg_fails_closed_on_stale_citation_artifacts_but_keeps_public_artifact_lean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(
                root,
                paper_text="\\section{Background}\n\nKnown needs current citation artifacts~\\cite{Known}.\n",
                citation_map={"Known": {"title": "Known Source", "url": "https://example.test/known"}},
            )
            write_rendered_reference_audit(root, quality_mode="claim_safe")
            rendered_path = rendered_reference_audit_path(root)
            rendered_payload = json.loads(rendered_path.read_text(encoding="utf-8"))
            rendered_payload["manuscript_sha256"] = "0" * 64
            rendered_payload["paper_full_tex_sha256"] = "0" * 64
            rendered_path.write_text(json.dumps(rendered_payload), encoding="utf-8")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])

            public_path, returned = ocq.write_citation_quality_gate(root, quality_mode="claim_safe")
            public_payload = json.loads(public_path.read_text(encoding="utf-8"))
            internal_payload = json.loads(_internal_cqg_path(self, root).read_text(encoding="utf-8"))

        for payload in (returned, public_payload):
            _assert_exact_lean_cqg(self, payload)
            self.assertEqual(payload["status"], "fail")
        self.assertIn("citation_quality_stale", internal_payload["hard_gate_failures"])
        self.assertTrue(any(failure["code"] == "citation_quality_stale" for failure in public_payload["failures"]))

    def test_smoke_custom_public_output_does_not_write_internal_artifact_next_to_custom_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            custom_dir = Path(tmp) / "custom-output"
            custom_dir.mkdir()
            _init_session(
                root,
                paper_text="\\section{Background}\n\nKnown is cited~\\cite{Known}.\n",
                citation_map={"Known": {"title": "Known Source", "url": "https://example.test/known"}},
            )
            write_rendered_reference_audit(root, quality_mode="claim_safe")
            custom_output = custom_dir / "public-cqg.json"

            custom_path, custom_payload = ocq.write_citation_quality_gate(root, quality_mode="claim_safe", output_path=custom_output)
            custom_written = json.loads(custom_output.read_text(encoding="utf-8"))
            sibling_internal = custom_dir / "citation_quality_gate.internal.json"
            sibling_internal_exists_after_custom = sibling_internal.exists()
            canonical_internal = _internal_cqg_path(self, root)
            canonical_exists_after_custom = canonical_internal.exists()
            canonical_path, canonical_payload = ocq.write_citation_quality_gate(root, quality_mode="claim_safe")
            canonical_exists_after_canonical = canonical_internal.exists()
            canonical_path_matches = canonical_path == ocq.citation_quality_gate_path(root)

        self.assertEqual(custom_path, custom_output.resolve())
        _assert_exact_lean_cqg(self, custom_payload)
        _assert_exact_lean_cqg(self, custom_written)
        self.assertFalse(sibling_internal_exists_after_custom)
        self.assertFalse(canonical_exists_after_custom)
        _assert_exact_lean_cqg(self, canonical_payload)
        self.assertTrue(canonical_exists_after_canonical)
        self.assertTrue(canonical_path_matches)
