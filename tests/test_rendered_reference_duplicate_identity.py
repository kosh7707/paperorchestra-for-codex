from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.citation_integrity import (
    build_rendered_reference_audit,
    citation_integrity_check,
    write_rendered_reference_audit,
)
from paperorchestra.models import InputBundle
from paperorchestra.session import artifact_path, create_session, load_session, save_session


def _init_session(root: Path) -> None:
    for name, content in {
        "idea.md": "# Idea\n",
        "experimental_log.md": "# Log\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Guidelines\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    state = create_session(
        root,
        InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            figures_dir=str(root / "figures"),
            cutoff_date="2024-11-01",
        ),
    )
    state.artifacts.paper_full_tex = str(artifact_path(root, "paper.full.tex"))
    state.artifacts.references_bib = str(artifact_path(root, "references.bib"))
    save_session(root, state)


def _entry(key: str, **fields: str) -> str:
    lines = [f"  {name} = {{{value}}}" for name, value in fields.items()]
    return "@article{" + key + ",\n" + ",\n".join(lines) + "\n}\n"


def _write_reference_case(root: Path, *, visible_keys: list[str], bib_entries: list[str]) -> None:
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text("Visible references " + " ".join(f"\\cite{{{key}}}" for key in visible_keys) + ".\n", encoding="utf-8")
    bbl = artifact_path(root, "paper.full.bbl")
    bbl.write_text("\n".join(f"\\bibitem{{{key}}} Rendered {key}." for key in visible_keys) + "\n", encoding="utf-8")
    refs = artifact_path(root, "references.bib")
    refs.write_text("\n".join(bib_entries), encoding="utf-8")
    state = load_session(root)
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.references_bib = str(refs)
    save_session(root, state)


def _duplicate_groups_by_keys(audit: dict) -> list[dict]:
    groups = audit.get("duplicate_identity_groups")
    if not isinstance(groups, list):
        return []
    return [group for group in groups if isinstance(group, dict)]


class RenderedReferenceDuplicateIdentityTests(unittest.TestCase):
    def test_visible_duplicate_doi_fails_rendered_reference_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["Alpha", "AlphaDup"],
                bib_entries=[
                    _entry("Alpha", title="Alpha", author="Ada", year="2024", doi="https://doi.org/10.1234/Example."),
                    _entry("AlphaDup", title="Alpha Copy", author="Ada", year="2024", doi="10.1234/example"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertEqual(audit["status"], "fail")
        self.assertIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertTrue(any(group.get("keys") == ["Alpha", "AlphaDup"] for group in groups), groups)
        self.assertTrue(any(group.get("identity") == "doi:10.1234/example" for group in groups), groups)

    def test_unused_duplicate_doi_does_not_fail_visible_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["Alpha"],
                bib_entries=[
                    _entry("Alpha", title="Alpha", author="Ada", year="2024", doi="10.1234/example"),
                    _entry("UnusedDup", title="Alpha Copy", author="Ada", year="2024", doi="10.1234/example"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertNotIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertFalse(any("UnusedDup" in group.get("keys", []) for group in groups), groups)

    def test_visible_duplicate_rfc_identity_fails_without_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["RFC8446A", "RFC8446B"],
                bib_entries=[
                    _entry("RFC8446A", title="TLS 1.3", author="IETF", year="2018", number="RFC 8446", organization="IETF"),
                    _entry("RFC8446B", title="TLS 1.3 Copy", author="IETF", year="2018", howpublished="RFC8446"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertEqual(audit["status"], "fail")
        self.assertIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertTrue(any(group.get("keys") == ["RFC8446A", "RFC8446B"] for group in groups), groups)
        self.assertTrue(any(group.get("identity") == "standard:rfc-8446" for group in groups), groups)

    def test_generic_report_numbers_without_namespace_do_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["ReportA", "ReportB"],
                bib_entries=[
                    _entry("ReportA", title="Annual Report A", author="Ada", year="2024", number="1"),
                    _entry("ReportB", title="Annual Report B", author="Bob", year="2024", reportnumber="1"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertNotIn("rendered_reference_duplicate_identity", audit["failing_codes"])

    def test_same_title_year_without_stable_identity_does_not_fail_duplicate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["One", "Two"],
                bib_entries=[
                    _entry("One", title="Common Title", author="Ada", year="2024"),
                    _entry("Two", title="Common Title", author="Bob", year="2024"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertNotIn("rendered_reference_duplicate_identity", audit["failing_codes"])

    def test_url_duplicate_identity_is_redacted_and_does_not_leak_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["UrlA", "UrlB"],
                bib_entries=[
                    _entry(
                        "UrlA",
                        title="URL A",
                        author="Ada",
                        year="2024",
                        url="https://user:SECRET@example.test/private/source.pdf?token=SECRET#frag",
                    ),
                    _entry("UrlB", title="URL B", author="Ada", year="2024", url="https://example.test/private/source.pdf"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertTrue(any(group.get("keys") == ["UrlA", "UrlB"] for group in groups), groups)
        rendered = json.dumps(audit.get("duplicate_identity_groups"), ensure_ascii=False)
        self.assertIn("url:", rendered)
        for forbidden in ["SECRET", "token=", "user:", "#frag", "example.test/private/source.pdf", "https://"]:
            self.assertNotIn(forbidden, rendered)

    def test_distinct_url_query_identities_do_not_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["SearchOne", "SearchTwo"],
                bib_entries=[
                    _entry("SearchOne", title="Search One", author="Ada", year="2024", url="https://example.test/search?id=1"),
                    _entry("SearchTwo", title="Search Two", author="Ada", year="2024", url="https://example.test/search?id=2"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertNotIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertFalse(any(group.get("keys") == ["SearchOne", "SearchTwo"] for group in groups), groups)

    def test_arxiv_eprint_and_arxiv_field_share_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["ArxivA", "ArxivB"],
                bib_entries=[
                    _entry(
                        "ArxivA",
                        title="Arxiv A",
                        author="Ada",
                        year="2024",
                        eprint="2401.01234",
                        archiveprefix="arXiv",
                    ),
                    _entry("ArxivB", title="Arxiv B", author="Ada", year="2024", arxiv="2401.01234"),
                ],
            )

            audit = build_rendered_reference_audit(root, quality_mode="claim_safe")

        self.assertIn("rendered_reference_duplicate_identity", audit["failing_codes"])
        groups = _duplicate_groups_by_keys(audit)
        self.assertTrue(any(group.get("keys") == ["ArxivA", "ArxivB"] for group in groups), groups)
        self.assertTrue(any(group.get("identity") == "arxiv:2401.01234" for group in groups), groups)

    def test_duplicate_rendered_reference_failure_propagates_to_citation_integrity_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_session(root)
            _write_reference_case(
                root,
                visible_keys=["Alpha", "AlphaDup"],
                bib_entries=[
                    _entry("Alpha", title="Alpha", author="Ada", year="2024", doi="10.1234/example"),
                    _entry("AlphaDup", title="Alpha Copy", author="Ada", year="2024", doi="10.1234/example"),
                ],
            )
            write_rendered_reference_audit(root, quality_mode="claim_safe")

            result = citation_integrity_check(root, load_session(root), quality_mode="claim_safe")

        self.assertIn("rendered_reference_duplicate_identity", result["failing_codes"])


if __name__ == "__main__":
    unittest.main()
