from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.citation_integrity import rendered_reference_audit_path, write_rendered_reference_audit
from paperorchestra.cli import main as cli_main
from paperorchestra.models import InputBundle
from paperorchestra.narrative import write_planning_artifacts
from paperorchestra.orchestra_citation_quality import (
    CITATION_QUALITY_GATE_SCHEMA_VERSION,
    build_citation_quality_gate,
    build_citation_quality_gate_internal,
    citation_quality_gate_path,
    write_citation_quality_gate,
)
from paperorchestra.orchestrator import run_until_blocked
from paperorchestra.quality_loop import build_quality_eval
from paperorchestra.quality_loop_plan_logic import _quality_eval_actions
from paperorchestra.quality_loop_policy import QA_LOOP_SUPPORTED_HANDLER_CODES
from paperorchestra.session import artifact_path, create_session, load_session, save_session


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _init_session(root: Path, *, cite_key: str = "Known", title: str = "Known Title", paper_text: str | None = None):
    for name, content in {
        "idea.md": "Synthetic idea for citation quality testing.\n",
        "experimental_log.md": "Synthetic experiment log.\n",
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
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text(paper_text or f"Synthetic claim~\\cite{{{cite_key}}}.\n", encoding="utf-8")
    refs = artifact_path(root, "references.bib")
    refs.write_text(
        f"""
        @article{{{cite_key},
          title = {{{title}}},
          author = {{Ada Example}},
          year = {{2026}},
          url = {{https://example.test/{cite_key}}}
        }}
        """,
        encoding="utf-8",
    )
    registry = artifact_path(root, "citation_registry.json")
    registry.write_text(
        json.dumps(
            [
                {
                    "paper_id": f"synthetic-{cite_key}",
                    "title": title,
                    "year": 2026,
                    "abstract": "Synthetic abstract.",
                    "authors": ["Ada Example"],
                    "citation_count": 1,
                    "bibtex_key": cite_key,
                }
            ]
        ),
        encoding="utf-8",
    )
    citation_map = artifact_path(root, "citation_map.json")
    citation_map.write_text(
        json.dumps({cite_key: {"title": title, "authors": ["Ada Example"], "year": 2026, "paper_id": f"synthetic-{cite_key}"}}),
        encoding="utf-8",
    )
    bbl = artifact_path(root, "paper.full.bbl")
    bbl.write_text(f"\\bibitem{{{cite_key}}} Rendered {cite_key}.\n", encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.references_bib = str(refs)
    state.artifacts.citation_registry_json = str(registry)
    state.artifacts.citation_map_json = str(citation_map)
    save_session(root, state)
    write_rendered_reference_audit(root, quality_mode="claim_safe")
    return load_session(root)


def _write_claim_map(root: Path, claims: list[dict]) -> Path:
    path = artifact_path(root, "claim_map.json")
    path.write_text(json.dumps({"claims": claims}), encoding="utf-8")
    state = load_session(root)
    state.artifacts.claim_map_json = str(path)
    save_session(root, state)
    return path


def _write_support_review(root: Path, items: list[dict]) -> Path:
    state = load_session(root)
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    path.write_text(json.dumps({"items": items, "evidence_mode": "web"}), encoding="utf-8")
    return path


def _write_source_support_review_v3(root: Path, cases: list[dict]) -> Path:
    state = load_session(root)
    path = Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    summary = {verdict: 0 for verdict in ("pass", "weak", "fail", "human_needed")}
    for case in cases:
        summary[str(case.get("verdict") or "human_needed")] += 1
    path.write_text(
        json.dumps(
            {
                "schema": "citation-support-review/3",
                "mode": "source",
                "summary": summary,
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )
    return path


def _attach_claim_safe_compile_report(root: Path) -> None:
    state = load_session(root)
    paper = Path(state.artifacts.paper_full_tex)
    pdf = artifact_path(root, "paper.full.pdf")
    pdf.write_bytes(b"%PDF-1.5\n% synthetic test pdf\n")
    compile_report = artifact_path(root, "compile-report.json")
    compile_report.write_text(
        json.dumps(
            {
                "clean": True,
                "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                "pdf_path": str(pdf),
                "pdf_exists": True,
                "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "warning_summary": [],
            }
        ),
        encoding="utf-8",
    )
    state.artifacts.compiled_pdf = str(pdf)
    state.artifacts.latest_compile_report_json = str(compile_report)
    save_session(root, state)


def _assert_exact_lean_cqg(test: unittest.TestCase, report: dict) -> None:
    test.assertEqual(set(report), {"schema", "status", "summary", "failures"})
    test.assertEqual(report["schema"], "citation-quality-gate/2")
    test.assertIn(report["status"], {"pass", "warn", "fail"})
    test.assertEqual(set(report["summary"]), {"pass", "weak", "fail", "human_needed"})
    for failure in report["failures"]:
        test.assertEqual(set(failure), {"case", "key", "code", "message"})


def _recursive_strings(value) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            strings.append(str(key))
            strings.extend(_recursive_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_recursive_strings(item))
    elif value is not None:
        strings.append(str(value))
    return strings


class CitationQualityGateTests(unittest.TestCase):
    def test_public_citation_quality_surfaces_are_exact_lean_schema_for_source_needed_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_RAW_CONTEXT needs a source~\\cite{Known}.",
                        "anchor": "PRIVATE_ANCHOR needs a source~\\cite{Known}.",
                        "target": "PRIVATE_TARGET needs a source",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "missing", "why": "unretrieved"},
                        "verdict": "human_needed",
                        "ask": "Place source.pdf under artifacts/references/C1/.",
                    }
                ],
            )
            public = build_citation_quality_gate(root, quality_mode="claim_safe")
            path, returned = write_citation_quality_gate(root, quality_mode="claim_safe")
            written = json.loads(path.read_text(encoding="utf-8"))
            cli_output = root / "citation-quality-cli.json"
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["audit-citation-quality", "--quality-mode", "claim_safe", "--output", str(cli_output)])
            cli_payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        for report in (public, returned, written, cli_payload["report"]):
            _assert_exact_lean_cqg(self, report)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["human_needed"], 1)
            self.assertEqual(len(report["failures"]), 1)
            self.assertEqual(report["failures"][0]["case"], "C1")
            self.assertEqual(report["failures"][0]["key"], "Known")
            self.assertEqual(report["failures"][0]["code"], "human_needed")
            self.assertIsInstance(report["failures"][0]["message"], str)
            self.assertNotIn("severity", report["failures"][0])
            for forbidden in {
                "schema_version",
                "quality_mode",
                "gate_summary",
                "manuscript_sha256",
                "hard_gate_failures",
                "warning_codes",
                "counts",
                "items",
                "acceptance_gate_impacts",
                "source_artifact_hashes",
                "private_safe_summary",
            }:
                self.assertNotIn(forbidden, report)

    def test_public_citation_quality_surfaces_do_not_leak_context_or_source_sentinels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="SOURCE_TITLE_SENTINEL")
            absolute_source = root / "absolute-source-sentinel.txt"
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_RAW_CONTEXT should stay private~\\cite{Known}.",
                        "anchor": "PRIVATE_ANCHOR should stay private~\\cite{Known}.",
                        "target": "PRIVATE_TARGET should stay private",
                        "source": {
                            "type": "paper",
                            "title": "SOURCE_TITLE_SENTINEL",
                            "url": "https://example.test/SOURCE_URL_SENTINEL",
                            "excerpt": "SOURCE_EXCERPT_SENTINEL",
                        },
                        "evidence": {"status": "missing", "path": str(absolute_source), "why": "blocked"},
                        "verdict": "human_needed",
                        "note": "NOTE_SENTINEL",
                        "ask": "ASK_SENTINEL artifacts/references/C1/source.pdf",
                    }
                ],
            )
            public = build_citation_quality_gate(root, quality_mode="claim_safe")
            path, returned = write_citation_quality_gate(root, quality_mode="claim_safe")
            written = json.loads(path.read_text(encoding="utf-8"))
            cli_output = root / "citation-quality-cli.json"
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                cli_main(["audit-citation-quality", "--quality-mode", "claim_safe", "--output", str(cli_output)])
            cli_payload = json.loads(stdout.getvalue())

        forbidden = {
            "PRIVATE_RAW_CONTEXT",
            "PRIVATE_ANCHOR",
            "PRIVATE_TARGET",
            "SOURCE_TITLE_SENTINEL",
            "SOURCE_URL_SENTINEL",
            "SOURCE_EXCERPT_SENTINEL",
            "NOTE_SENTINEL",
            "ASK_SENTINEL",
            "FAILURE_MESSAGE_SENTINEL",
            "artifacts/references/",
            str(root),
            "items",
            "source_artifact_hashes",
            "manuscript_sha256",
            "paragraph",
            "anchor",
            "target",
        }
        for report in (public, returned, written, cli_payload["report"]):
            _assert_exact_lean_cqg(self, report)
            all_strings = _recursive_strings(report)
            for text in all_strings:
                self.assertNotIn("sha256", text.lower())
                self.assertNotIn("hash", text.lower())
            rendered = json.dumps(report, ensure_ascii=False)
            for sentinel in forbidden:
                self.assertNotIn(sentinel, rendered)

    def test_internal_citation_quality_api_preserves_routing_fields_after_public_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "A critical claim needs a source~\\cite{Known}.",
                        "anchor": "A critical claim needs a source~\\cite{Known}.",
                        "target": "A critical claim needs a source",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "missing", "why": "unretrieved"},
                        "verdict": "human_needed",
                        "ask": "Provide a source artifact.",
                    }
                ],
            )

            internal = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            public = build_citation_quality_gate(root, quality_mode="claim_safe")

        _assert_exact_lean_cqg(self, internal["public_report"])
        self.assertEqual(internal["public_report"], public)
        self.assertEqual(internal["status"], "fail")
        self.assertIn("critical_unsupported_citation", internal["hard_gate_failures"])
        for field in {
            "critical_unsupported_count",
            "critical_need_count",
            "critical_weak_identity_count",
            "noncritical_weak_identity_count",
            "citation_bomb_count",
            "duplicate_reference_count",
        }:
            self.assertIn(field, internal["counts"])
        self.assertIsInstance(internal["items"], list)
        self.assertIn("acceptance_gate_impacts", internal)

    def test_quality_eval_consumes_internal_citation_quality_but_keeps_persisted_artifact_lean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _attach_claim_safe_compile_report(root)
            write_planning_artifacts(root)
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "A critical claim needs a source~\\cite{Known}.",
                        "anchor": "A critical claim needs a source~\\cite{Known}.",
                        "target": "A critical claim needs a source",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "missing", "why": "unretrieved"},
                        "verdict": "human_needed",
                        "ask": "Provide a source artifact.",
                    }
                ],
            )
            write_citation_quality_gate(root, quality_mode="claim_safe")
            reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
            with patch("paperorchestra.quality_loop.build_reproducibility_audit", return_value=reproducibility), patch(
                "paperorchestra.quality_loop.planning_artifact_status",
                return_value={"status": "pass", "failing_codes": [], "artifacts": {}},
            ), patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
                payload = build_quality_eval(root, quality_mode="claim_safe", reproducibility=reproducibility)
            gate = payload["tiers"]["tier_2_claim_safety"]["checks"]["citation_quality_gate"]
            written = json.loads(citation_quality_gate_path(root).read_text(encoding="utf-8"))

        self.assertEqual(payload["tiers"]["tier_1_structural"]["status"], "pass")
        self.assertEqual(payload["tiers"]["tier_2_claim_safety"]["status"], "fail")
        self.assertIn("critical_unsupported_citation", payload["tiers"]["tier_2_claim_safety"]["failing_codes"])
        self.assertEqual(gate["status"], "fail")
        self.assertIn("hard_gate_failures", gate)
        self.assertIn("counts", gate)
        self.assertIn("public_report", gate)
        _assert_exact_lean_cqg(self, gate["public_report"])
        _assert_exact_lean_cqg(self, written)
        self.assertIn("citation_quality_gate_sha256", payload["source_artifacts"])
        self.assertNotIn("citation_quality_gate", payload["source_artifacts"])

    def test_claim_safe_unknown_metadata_for_critical_claim_is_hard_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(
                root,
                [
                    {
                        "id": "C1",
                        "claim_type": "numeric",
                        "graph_role": "root",
                        "required": True,
                        "citation_required": True,
                        "citation_keys": ["UnknownMeta"],
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["schema_version"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertEqual(report["acceptance_gate_impacts"]["no_unknown_refs_for_critical_claims"], "fail")
        self.assertNotIn(tmp, rendered)

    def test_same_unknown_metadata_is_warning_when_explicitly_noncritical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(
                root,
                [
                    {
                        "id": "BG1",
                        "claim_type": "background",
                        "graph_role": "background",
                        "required": False,
                        "citation_required": False,
                        "citation_keys": ["UnknownMeta"],
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "warn")
        self.assertNotIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertIn("noncritical_unknown_reference", report["warning_codes"])

    def test_unsupported_or_metadata_only_support_for_critical_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "PRIVATE_RAW_SENTENCE_SHOULD_NOT_LEAK~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "metadata_only",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unsupported_citation", report["hard_gate_failures"])
        self.assertNotIn("PRIVATE_RAW_SENTENCE_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("Known Title", rendered)
        self.assertNotIn(tmp, rendered)

    def test_supported_critical_citation_with_known_metadata_passes_hard_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "Synthetic supported sentence~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "supported",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["hard_gate_failures"], [])
        self.assertEqual(report["counts"]["critical_unsupported_count"], 0)

    def test_source_backed_v3_pass_supports_critical_citation_without_raw_context_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_RAW_CONTEXT should never appear~\\cite{Known}.",
                        "anchor": "PRIVATE_RAW_CONTEXT should never appear~\\cite{Known}.",
                        "target": "PRIVATE_RAW_CONTEXT should never appear",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "text", "text": "artifacts/references/C1/source.txt"},
                        "verdict": "pass",
                        "note": "Supported by source text.",
                    }
                ],
            )
            artifact_path(root, "references/C1/source.txt").write_text(
                "Known source text supports the cited critical claim.",
                encoding="utf-8",
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["schema_version"], "citation-quality-gate/2")
        self.assertEqual(report["schema"], "citation-quality-gate/2")
        self.assertEqual(report["summary"], {"pass": 1, "weak": 0, "fail": 0, "human_needed": 0})
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["hard_gate_failures"], [])
        self.assertNotIn("PRIVATE_RAW_CONTEXT", rendered)
        self.assertNotIn("Known Title", rendered)
        self.assertNotIn(tmp, rendered)

    def test_source_backed_v3_pass_without_readable_artifact_fails_claim_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_RAW_CONTEXT should never appear~\\cite{Known}.",
                        "anchor": "PRIVATE_RAW_CONTEXT should never appear~\\cite{Known}.",
                        "target": "PRIVATE_RAW_CONTEXT should never appear",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "text", "text": "artifacts/references/C1/source.txt"},
                        "verdict": "pass",
                        "note": "Claimed supported, but source text is missing.",
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unsupported_citation", report["hard_gate_failures"])
        self.assertIn("critical_unsupported_citation", [failure["code"] for failure in report["failures"]])
        self.assertEqual(report["summary"]["human_needed"], 1)
        self.assertNotIn("PRIVATE_RAW_CONTEXT", rendered)
        self.assertNotIn("Known Title", rendered)
        self.assertNotIn(tmp, rendered)

    def test_source_backed_v3_human_needed_blocks_critical_citation_without_raw_context_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["Known"]}])
            _write_source_support_review_v3(
                root,
                [
                    {
                        "id": "C1",
                        "key": "Known",
                        "loc": "Background ¶1",
                        "paragraph": "PRIVATE_RAW_CONTEXT needs a source~\\cite{Known}.",
                        "anchor": "PRIVATE_RAW_CONTEXT needs a source~\\cite{Known}.",
                        "target": "PRIVATE_RAW_CONTEXT needs a source",
                        "source": {"type": "paper", "title": "Known Title"},
                        "evidence": {"status": "missing", "why": "unretrieved"},
                        "verdict": "human_needed",
                        "ask": "Place source.pdf under artifacts/references/C1/.",
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")
            rendered = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unsupported_citation", report["hard_gate_failures"])
        self.assertNotIn("PRIVATE_RAW_CONTEXT", rendered)
        self.assertNotIn("Known Title", rendered)
        self.assertNotIn(tmp, rendered)

    def test_claim_safe_missing_rendered_metadata_for_critical_citation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            rendered_reference_audit_path(root).unlink()
            _write_support_review(
                root,
                [
                    {
                        "id": "support-1",
                        "sentence": "Synthetic supported sentence~\\cite{Known}.",
                        "citation_keys": ["Known"],
                        "support_status": "supported",
                        "critical": True,
                    }
                ],
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_citation_metadata_missing", report["hard_gate_failures"])

    def test_noncritical_duplicate_warning_does_not_mask_critical_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="UnknownMeta", title="Unknown")
            _write_claim_map(root, [{"id": "C1", "claim_type": "numeric", "required": True, "citation_keys": ["UnknownMeta"]}])
            integrity = artifact_path(root, "citation_integrity.audit.json")
            integrity.write_text(
                json.dumps(
                    {
                        "schema_version": "citation-integrity-audit/1",
                        "status": "fail",
                        "manuscript_sha256": "stale-is-tested-elsewhere",
                        "failing_codes": ["citation_duplicate_support", "citation_bomb_detected"],
                        "checks": {
                            "duplicate_support": {"duplicate_keys": ["Repeated"]},
                            "citation_density": {"bomb_sentences": [{"citation_keys": ["A", "B", "C", "D"]}]},
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_unknown_reference", report["hard_gate_failures"])
        self.assertIn("citation_duplicate_support", report["warning_codes"])
        self.assertIn("citation_bomb_detected", report["warning_codes"])

    def test_missing_support_evidence_for_critical_need_fails_claim_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            _write_claim_map(root, [{"id": "C1", "claim_type": "novelty", "required": True, "citation_required": True, "citation_keys": ["Known"]}])

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("critical_citation_support_missing", report["hard_gate_failures"])

    def test_stale_rendered_reference_audit_fails_claim_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            rendered_path = rendered_reference_audit_path(root)
            payload = json.loads(rendered_path.read_text(encoding="utf-8"))
            payload["manuscript_sha256"] = "0" * 64
            payload["paper_full_tex_sha256"] = "0" * 64
            rendered_path.write_text(json.dumps(payload), encoding="utf-8")

            report = build_citation_quality_gate_internal(root, quality_mode="claim_safe")

        self.assertEqual(report["status"], "fail")
        self.assertIn("citation_quality_stale", report["hard_gate_failures"])

    def test_cli_writes_citation_quality_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            output = root / "citation-quality.json"
            stdout = io.StringIO()
            with _chdir(root), contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["audit-citation-quality", "--quality-mode", "claim_safe", "--output", str(output)])
            payload = json.loads(stdout.getvalue())
            output_exists = output.exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_exists)
        _assert_exact_lean_cqg(self, payload["report"])
        self.assertEqual(payload["report"]["schema"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertEqual(Path(payload["path"]), output)

    def test_quality_eval_includes_citation_quality_gate_without_raw_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root, cite_key="Known", title="Known Title")
            write_planning_artifacts(root)

            payload = build_quality_eval(root, quality_mode="ralph")
            gate = payload["tiers"]["tier_2_claim_safety"]["checks"]["citation_quality_gate"]
            rendered = json.dumps(gate, ensure_ascii=False)

        self.assertEqual(gate["schema_version"], CITATION_QUALITY_GATE_SCHEMA_VERSION)
        self.assertNotIn("citation_quality_gate", payload["source_artifacts"])
        self.assertIn("citation_quality_gate_sha256", payload["source_artifacts"])
        self.assertNotIn(str(root), rendered)
        self.assertNotIn("Synthetic claim", rendered)
        self.assertNotIn("Known Title", rendered)

    def test_quality_loop_plan_routes_critical_citation_quality_to_machine_work(self) -> None:
        quality_eval = {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_quality_gate": {
                            "status": "fail",
                            "hard_gate_failures": [
                                "citation_quality_stale",
                                "critical_unknown_reference",
                                "critical_unsupported_citation",
                                "critical_citation_support_missing",
                                "critical_weak_reference_identity",
                            ],
                            "counts": {
                                "critical_unsupported_count": 1,
                                "critical_need_count": 1,
                                "critical_weak_identity_count": 1,
                                "noncritical_weak_identity_count": 0,
                                "citation_bomb_count": 0,
                                "duplicate_reference_count": 0,
                            },
                            "public_report": {
                                "schema": "citation-quality-gate/2",
                                "status": "fail",
                                "summary": {"pass": 0, "weak": 0, "fail": 0, "human_needed": 1},
                                "failures": [
                                    {"case": "C1", "key": "Known", "code": "human_needed", "message": "Source required."}
                                ],
                            },
                        }
                    },
                    "failing_codes": [
                        "citation_quality_stale",
                        "critical_unknown_reference",
                        "critical_unsupported_citation",
                        "critical_citation_support_missing",
                        "critical_weak_reference_identity",
                    ],
                }
            }
        }

        actions = _quality_eval_actions(quality_eval)
        expected_codes = {
            "critical_unknown_reference",
            "critical_unsupported_citation",
            "critical_citation_support_missing",
            "critical_weak_reference_identity",
            "citation_quality_stale",
        }
        citation_actions = [action for action in actions if str(action.get("code")) in expected_codes]

        self.assertEqual({action.get("code") for action in citation_actions}, expected_codes)
        self.assertTrue(all(action.get("automation") in {"automatic", "semi_auto"} for action in citation_actions))
        self.assertFalse(any(action.get("automation") == "human_needed" for action in citation_actions))
        self.assertTrue(
            {
                "critical_unknown_reference",
                "critical_missing_bib_entry",
                "critical_unsupported_citation",
                "critical_citation_support_missing",
                "critical_weak_reference_identity",
            }.issubset(QA_LOOP_SUPPORTED_HANDLER_CODES)
        )

    def test_machine_solvable_citation_gap_remains_research_routed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("We introduce a new synthetic workflow that improves review reliability by 12 percent.\n", encoding="utf-8")
            (material / "experiment_log.md").write_text("Synthetic experiment notes.\n", encoding="utf-8")
            (material / "references.bib").write_text("@article{unknown2026, title={Unknown}, author={Anonymous}, year={TODO}}\n", encoding="utf-8")

            state = run_until_blocked(root, material_path=material)

        self.assertNotEqual(state.facets.interaction, "human_needed")
        self.assertIn(state.next_actions[0].action_type, {"start_autoresearch", "start_autoresearch_goal"})

    def test_default_gate_path_is_session_artifact_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            path = citation_quality_gate_path(root)

        self.assertEqual(path.name, "citation_quality_gate.json")
        self.assertIn(".paper-orchestra", str(path))


if __name__ == "__main__":
    unittest.main()
