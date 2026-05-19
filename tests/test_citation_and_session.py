from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.literature import (
    ensure_unique_bibtex_keys,
    load_prior_work_seed,
    make_bibtex_key,
    paper_citable_metadata_failures,
    registry_to_bibtex,
    title_match_ratio,
    year_month_passes_cutoff,
)
from paperorchestra.io_utils import read_json, write_json
from paperorchestra.models import InputBundle, VerifiedPaper
from paperorchestra.pipeline import build_bib
from paperorchestra.session import artifact_path, create_session, load_session, save_session


class CitationTests(unittest.TestCase):
    def test_bibtex_generation(self) -> None:
        paper = VerifiedPaper(
            paper_id="abc",
            title="A Great Paper",
            year=2024,
            publication_date=None,
            venue="ICLR",
            abstract="abstract",
            authors=["Jane Doe", "John Smith"],
            citation_count=10,
            url="https://example.com",
        )
        paper.bibtex_key = make_bibtex_key(paper)
        bib = registry_to_bibtex([paper])
        self.assertIn("@inproceedings", bib)
        self.assertIn("A Great Paper", bib)
        self.assertIn(paper.bibtex_key, bib)

    def test_title_match_ratio_is_high_for_close_titles(self) -> None:
        ratio = title_match_ratio("PaperOrchestra: A Multi-Agent Framework", "PaperOrchestra A Multi Agent Framework")
        self.assertGreater(ratio, 90.0)

    def test_cutoff_enforces_exact_date_when_publication_date_known(self) -> None:
        self.assertFalse(year_month_passes_cutoff(2024, "2024-03-01", "2024-12-01"))

    def test_journal_entry_uses_article_type(self) -> None:
        paper = VerifiedPaper(
            paper_id="def",
            title="Journal Example",
            year=2024,
            publication_date=None,
            venue="Journal of Testing",
            abstract="abstract",
            authors=["Jane Doe"],
            citation_count=5,
        )
        paper.bibtex_key = make_bibtex_key(paper)
        bib = registry_to_bibtex([paper])
        self.assertIn("@article", bib)
        self.assertIn("journal = {Journal of Testing}", bib)

    def test_ensure_unique_bibtex_keys_disambiguates_collisions(self) -> None:
        first = VerifiedPaper(
            paper_id="a",
            title="A Survey on Testing",
            year=2024,
            publication_date=None,
            venue="ICLR",
            abstract="abstract",
            authors=["Jane Doe"],
            citation_count=1,
        )
        second = VerifiedPaper(
            paper_id="b",
            title="A Survey on Testing in Practice",
            year=2024,
            publication_date=None,
            venue="ICLR",
            abstract="abstract",
            authors=["Jane Doe"],
            citation_count=1,
        )
        first.bibtex_key = make_bibtex_key(first)
        second.bibtex_key = make_bibtex_key(second)
        ensure_unique_bibtex_keys([first, second])
        self.assertNotEqual(first.bibtex_key, second.bibtex_key)
        bib = registry_to_bibtex([first, second])
        self.assertEqual(bib.count("@inproceedings"), 2)

    def test_bibtex_key_sanitizes_latex_author_markup(self) -> None:
        paper = VerifiedPaper(
            paper_id="p-latex-author",
            title="Benchmarking of Symmetric Ciphers",
            year=2022,
            publication_date=None,
            venue="Benchmark",
            abstract="abstract",
            authors=['B{\\"u}hler'],
            citation_count=None,
        )
        self.assertEqual(make_bibtex_key(paper), "buhler2022BenchmarkingOfSymmetric")

    def test_bibtex_seed_parser_preserves_nested_braces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refs.bib"
            path.write_text(
                "@techreport{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018},\n"
                "  url = {https://www.rfc-editor.org/info/rfc8446}\n"
                "}\n",
                encoding="utf-8",
            )
            entries = load_prior_work_seed(path, source="manual_bibtex")
        self.assertEqual(entries[0]["title"], "The Transport Layer Security ({TLS}) Protocol Version 1.3")

    def test_bibtex_seed_ignores_non_doi_url_parameter_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refs.bib"
            path.write_text(
                "@article{md5,\n"
                "  title = {Message Authentication with {MD5}},\n"
                "  author = {Burt Kaliski and Matthew J. B. Robshaw},\n"
                "  year = {1995},\n"
                "  journal = {CryptoBytes},\n"
                "  url = {https://citeseerx.ist.psu.edu/document?doi=cad36d5c4fdf768154b7bfafa5e1a33a1abf0062},\n"
                "}\n",
                encoding="utf-8",
            )
            entries = load_prior_work_seed(path, source="manual_bibtex")
        self.assertEqual(entries[0]["external_ids"], {})

    def test_bibtex_seed_preserves_original_bibtex_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refs.bib"
            path.write_text(
                "@inproceedings{RFC8446,\n"
                "  title = {The Transport Layer Security ({TLS}) Protocol Version 1.3},\n"
                "  author = {Eric Rescorla},\n"
                "  year = {2018},\n"
                "  url = {https://www.rfc-editor.org/info/rfc8446}\n"
                "}\n",
                encoding="utf-8",
            )
            entries = load_prior_work_seed(path, source="manual_bibtex")
        self.assertEqual(entries[0]["bibtex_key"], "RFC8446")

    def test_registry_to_bibtex_escapes_special_value_characters(self) -> None:
        paper = VerifiedPaper(
            paper_id="p-special",
            title="R&D 100% _safe_ paper #1",
            year=2024,
            publication_date=None,
            venue="Journal of A&B Systems",
            abstract="abstract",
            authors=['B{\\"u}hler', "Alice & Bob"],
            citation_count=1,
            url="https://example.com/query?a=1&b=2",
            external_ids={"DOI": "10.1000/a_b%2"},
        )
        paper.bibtex_key = make_bibtex_key(paper)
        bib = registry_to_bibtex([paper])
        self.assertIn(r"title = {R\&D 100\% \_safe\_ paper \#1}", bib)
        self.assertIn(r'author = {B{\"u}hler and Alice \& Bob}', bib)
        self.assertIn(r"journal = {Journal of A\&B Systems}", bib)
        self.assertIn(r"url = {https://example.com/query?a=1\&b=2}", bib)
        self.assertIn(r"doi = {10.1000/a\_b\%2}", bib)

    def test_registry_to_bibtex_rejects_unbalanced_bibtex_values(self) -> None:
        paper = VerifiedPaper(
            paper_id="p-invalid-bib",
            title="Unsafe {title",
            year=2024,
            publication_date=None,
            venue="ICLR",
            abstract="abstract",
            authors=["Jane Doe"],
            citation_count=1,
        )
        paper.bibtex_key = make_bibtex_key(paper)
        with self.assertRaisesRegex(ValueError, "unbalanced braces"):
            registry_to_bibtex([paper])

    def test_registry_to_bibtex_omits_uncitable_unknown_metadata_instead_of_rendering_unknown(self) -> None:
        incomplete = VerifiedPaper(
            paper_id="p-incomplete",
            title="Unknown",
            year=None,
            publication_date=None,
            venue=None,
            abstract="abstract",
            authors=[],
            citation_count=None,
        )
        incomplete.bibtex_key = "unknown2026"

        bib = registry_to_bibtex([incomplete])

        self.assertEqual(bib, "")
        self.assertNotIn("Unknown", bib)
        self.assertEqual(
            paper_citable_metadata_failures(incomplete),
            ["title_unknown", "year_unknown"],
        )

    def test_registry_to_bibtex_keeps_traceable_reference_without_unknown_venue_placeholder(self) -> None:
        paper = VerifiedPaper(
            paper_id="p-traceable",
            title="Traceable Reference Without Venue",
            year=2024,
            publication_date=None,
            venue=None,
            abstract="abstract",
            authors=["Ada Example"],
            citation_count=1,
            url="https://example.test/traceable",
        )
        paper.bibtex_key = "traceable2024"

        bib = registry_to_bibtex([paper])

        self.assertIn("@inproceedings{traceable2024", bib)
        self.assertIn("url = {https://example.test/traceable}", bib)
        self.assertNotIn("Unknown", bib)
        self.assertNotIn("Unknown Venue", bib)

    def test_registry_to_bibtex_omits_explicit_unknown_author_placeholder(self) -> None:
        paper = VerifiedPaper(
            paper_id="p-unknown-author",
            title="Known Title",
            year=2024,
            publication_date=None,
            venue="Known Venue",
            abstract="abstract",
            authors=["Unknown"],
            citation_count=1,
        )
        paper.bibtex_key = "unknownAuthor2024"

        bib = registry_to_bibtex([paper])

        self.assertEqual(bib, "")
        self.assertEqual(paper_citable_metadata_failures(paper), ["author_or_organization_unknown"])

    def test_build_bib_filters_uncitable_registry_entries_from_bib_and_citation_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {}
            for name in ["idea.md", "experimental_log.md", "template.tex", "guidelines.md"]:
                path = root / name
                path.write_text(f"content for {name}\n", encoding="utf-8")
                inputs[name] = path
            state = create_session(
                root,
                InputBundle(
                    idea_path=str(inputs["idea.md"]),
                    experimental_log_path=str(inputs["experimental_log.md"]),
                    template_path=str(inputs["template.tex"]),
                    guidelines_path=str(inputs["guidelines.md"]),
                ),
            )
            good = VerifiedPaper(
                paper_id="p-good",
                title="Good Reference",
                year=2024,
                publication_date=None,
                venue="Good Venue",
                abstract="abstract",
                authors=["Ada Example"],
                citation_count=1,
                url="https://example.test/good",
            )
            good.bibtex_key = "good2024"
            bad = VerifiedPaper(
                paper_id="p-bad",
                title="Unknown",
                year=None,
                publication_date=None,
                venue=None,
                abstract="abstract",
                authors=[],
                citation_count=None,
            )
            bad.bibtex_key = "bad2024"
            registry_path = artifact_path(root, "citation_registry.json")
            write_json(registry_path, [good.to_dict(), bad.to_dict()])
            state.artifacts.citation_registry_json = str(registry_path)
            save_session(root, state)

            references_path = build_bib(root)
            state = load_session(root)
            bib = references_path.read_text(encoding="utf-8")
            citation_map = read_json(state.artifacts.citation_map_json)

        self.assertIn("good2024", bib)
        self.assertNotIn("bad2024", bib)
        self.assertNotIn("Unknown", bib)
        self.assertIn("good2024", citation_map)
        self.assertNotIn("bad2024", citation_map)


class SessionTests(unittest.TestCase):
    def test_session_init_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {}
            for name in ["idea.md", "experimental_log.md", "template.tex", "guidelines.md"]:
                path = root / name
                path.write_text(f"content for {name}\n", encoding="utf-8")
                inputs[name] = path
            state = create_session(
                root,
                InputBundle(
                    idea_path=str(inputs["idea.md"]),
                    experimental_log_path=str(inputs["experimental_log.md"]),
                    template_path=str(inputs["template.tex"]),
                    guidelines_path=str(inputs["guidelines.md"]),
                    cutoff_date="2024-11-01",
                ),
            )
            loaded = load_session(root, state.session_id)
            self.assertEqual(loaded.session_id, state.session_id)
            self.assertEqual(loaded.inputs.cutoff_date, "2024-11-01")

    def test_session_allows_outside_workspace_only_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tempfile.mkdtemp())
            try:
                for name in ["idea.md", "experimental_log.md", "template.tex", "guidelines.md"]:
                    (outside / name).write_text("content\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    create_session(
                        root,
                        InputBundle(
                            idea_path=str(outside / "idea.md"),
                            experimental_log_path=str(outside / "experimental_log.md"),
                            template_path=str(outside / "template.tex"),
                            guidelines_path=str(outside / "guidelines.md"),
                        ),
                    )
            finally:
                for item in outside.iterdir():
                    item.unlink()
                outside.rmdir()


if __name__ == "__main__":
    unittest.main()
