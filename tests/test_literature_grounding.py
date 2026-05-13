from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import build_parser
from paperorchestra.io_utils import read_json
from paperorchestra.literature import build_search_grounded_candidates, search_openalex
from paperorchestra.models import InputBundle, VerifiedPaper
from paperorchestra.pipeline import _experimental_log_search_queries, build_bib, discover_papers, generate_outline, import_prior_work, verify_papers
from paperorchestra.providers import MockProvider
from paperorchestra.session import create_session, load_session


class SearchGroundingTests(unittest.TestCase):
    def test_openalex_search_does_not_send_semantic_scholar_api_key(self) -> None:
        captured_headers: dict[str, str] = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"results": []}'

        def fake_urlopen(request, timeout):
            captured_headers.update(dict(request.header_items()))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "openalex-cache.json"
            with patch.dict("os.environ", {"SEMANTIC_SCHOLAR_API_KEY": "secret-key"}, clear=False), patch(
                "paperorchestra.literature._cache_path",
                return_value=cache_path,
            ), patch("paperorchestra.literature.urllib.request.urlopen", side_effect=fake_urlopen):
                self.assertEqual(search_openalex("streaming mode encryption", limit=1), [])

        lowered = {key.lower(): value for key, value in captured_headers.items()}
        self.assertNotIn("x-api-key", lowered)

    def test_search_grounded_candidates_merge_sources_and_dedupe(self) -> None:
        queries = ["macro query", "micro query"]
        with patch(
            "paperorchestra.literature.search_semantic_scholar",
            side_effect=[
                [
                    {"title": "Alpha Paper", "abstract": "alpha abstract", "year": 2024, "publicationDate": "2024-01-01"},
                    {"title": "Shared Paper", "abstract": "shared from scholar", "year": 2024, "publicationDate": "2024-01-01"},
                ],
                [
                    {"title": "Micro Scholar Paper", "abstract": "micro abstract", "year": 2024, "publicationDate": "2024-01-01"},
                ],
            ],
        ), patch(
            "paperorchestra.literature.search_openalex",
            side_effect=[
                [
                    {"display_name": "Shared Paper", "publication_year": 2024, "publication_date": "2024-02-01", "abstract_inverted_index": {"shared": [0], "openalex": [1]}},
                    {"display_name": "OpenAlex Only", "publication_year": 2024, "publication_date": "2024-03-01", "abstract_inverted_index": {"openalex": [0], "only": [1]}},
                ],
                [
                    {"display_name": "Micro OpenAlex", "publication_year": 2024, "publication_date": "2024-04-01", "abstract_inverted_index": {"micro": [0], "openalex": [1]}},
                ],
            ],
        ):
            payload, notes = build_search_grounded_candidates(
                queries,
                macro_query_count=1,
                cutoff_date="2025-01-01",
                per_source_limit=2,
            )

        macro_titles = [item["title_guess"] for item in payload["macro_candidates"]]
        micro_titles = [item["title_guess"] for item in payload["micro_candidates"]]
        self.assertEqual(macro_titles, ["Alpha Paper", "Shared Paper", "OpenAlex Only"])
        self.assertEqual(micro_titles, ["Micro Scholar Paper", "Micro OpenAlex"])
        self.assertEqual(payload["macro_candidates"][2]["discovery_source"], "openalex")
        self.assertEqual(payload["macro_candidates"][1]["discovery_sources"], ["semantic_scholar", "openalex"])
        self.assertIn("Semantic Scholar grounded query completed: macro query", notes)
        self.assertIn("OpenAlex grounded query completed: micro query", notes)

    def test_search_grounded_candidates_respect_cutoff(self) -> None:
        with patch(
            "paperorchestra.literature.search_semantic_scholar",
            return_value=[{"title": "Too New", "abstract": "x", "year": 2025, "publicationDate": "2025-02-01"}],
        ), patch(
            "paperorchestra.literature.search_openalex",
            return_value=[{"display_name": "Old Enough", "publication_year": 2024, "publication_date": "2024-02-01", "abstract_inverted_index": {"old": [0]}}],
        ):
            payload, _ = build_search_grounded_candidates(["query"], macro_query_count=1, cutoff_date="2025-01-01")

        self.assertEqual([item["title_guess"] for item in payload["macro_candidates"]], ["Old Enough"])

    def test_search_grounded_candidates_filter_irrelevant_live_hits(self) -> None:
        with patch(
            "paperorchestra.literature.search_semantic_scholar",
            return_value=[
                {
                    "title": "Scientific article generation with citation coverage constraints",
                    "abstract": "Scientific article generation with strong citation coverage constraints and failure analysis for single-loop drafting.",
                    "year": 2024,
                    "publicationDate": "2024-01-01",
                }
            ],
        ), patch(
            "paperorchestra.literature.search_openalex",
            return_value=[
                {
                    "display_name": "Global burden of disease study",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "abstract_inverted_index": {"global": [0], "burden": [1], "disease": [2]},
                },
                {
                    "display_name": "Testing of detection tools for AI-generated text",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "abstract_inverted_index": {"scientific": [0], "writing": [1], "ai": [2], "generated": [3], "text": [4]},
                },
            ],
        ):
            payload, _ = build_search_grounded_candidates(
                ["LLM scientific article generation single loop failure citation coverage"],
                macro_query_count=1,
                cutoff_date="2025-01-01",
            )

        self.assertEqual(
            [item["title_guess"] for item in payload["macro_candidates"]],
            [
                "Scientific article generation with citation coverage constraints",
            ],
        )

    def test_search_grounded_candidates_preserve_exact_seed_when_live_results_do_not_match(self) -> None:
        with patch(
            "paperorchestra.literature.search_semantic_scholar",
            return_value=[
                {
                    "title": "Single-Agent Pixantrone as a Bridge to Autologous Stem Cell Transplantation",
                    "abstract": "Medical oncology paper.",
                    "year": 2024,
                    "publicationDate": "2024-01-01",
                }
            ],
        ), patch(
            "paperorchestra.literature.search_openalex",
            return_value=[
                {
                    "display_name": "Efficacy and Safety of Trastuzumab as a Single Agent",
                    "publication_year": 2024,
                    "publication_date": "2024-01-01",
                    "abstract_inverted_index": {"single": [0], "agent": [1], "trial": [2]},
                }
            ],
        ):
            payload, notes = build_search_grounded_candidates(
                ["Single Agent"],
                macro_query_count=1,
                cutoff_date="2025-01-01",
            )

        self.assertEqual([item["title_guess"] for item in payload["macro_candidates"]], ["Single Agent"])
        self.assertEqual(payload["macro_candidates"][0]["discovery_source"], "session_seed")
        self.assertIn("Exact grounded seed preserved without matching live result: Single Agent", notes)

    def test_search_grounded_candidates_preserve_benchmark_seed_with_digits(self) -> None:
        benchmark = "PaperWritingBench (200 papers from CVPR 2025 and ICLR 2025)"
        with patch(
            "paperorchestra.literature.search_semantic_scholar",
            return_value=[
                {
                    "title": "Benchmarking manuscript generation quality",
                    "abstract": "A generic benchmark paper.",
                    "year": 2024,
                    "publicationDate": "2024-01-01",
                }
            ],
        ), patch(
            "paperorchestra.literature.search_openalex",
            return_value=[],
        ):
            payload, notes = build_search_grounded_candidates(
                [benchmark],
                macro_query_count=1,
                cutoff_date="2025-01-01",
            )

        self.assertEqual([item["title_guess"] for item in payload["macro_candidates"]], [benchmark])
        self.assertEqual(payload["macro_candidates"][0]["discovery_source"], "session_seed")
        self.assertIn(f"Exact grounded seed preserved without matching live result: {benchmark}", notes)

    def test_cli_accepts_search_grounded_discovery_mode(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["job-start-run", "--discovery-mode", "search-grounded"])
        self.assertEqual(args.discovery_mode, "search-grounded")
        args = parser.parse_args(["job-start-run", "--verify-error-policy", "fail"])
        self.assertEqual(args.verify_error_policy, "fail")
        args = parser.parse_args(["job-start-run", "--verify-fallback-mode", "mock"])
        self.assertEqual(args.verify_fallback_mode, "mock")
        args = parser.parse_args(["discover-papers", "--mode", "search-grounded"])
        self.assertEqual(args.mode, "search-grounded")
        args = parser.parse_args(["import-prior-work", "--seed-file", "prior.json", "--source", "codex_web_seed"])
        self.assertEqual(args.seed_file, "prior.json")
        self.assertEqual(args.source, "codex_web_seed")
        args = parser.parse_args(["import-prior-work", "--seed-file", "prior.json", "--require-complete-metadata"])
        self.assertTrue(args.require_complete_metadata)
        args = parser.parse_args(["research-prior-work", "--provider", "mock", "--import"])
        self.assertEqual(args.provider, "mock")
        self.assertTrue(args.import_seed)
        args = parser.parse_args(["research-prior-work", "--provider", "mock", "--import", "--require-complete-metadata"])
        self.assertTrue(args.require_complete_metadata)
        args = parser.parse_args(["verify-papers", "--on-error", "fail"])
        self.assertEqual(args.on_error, "fail")
        args = parser.parse_args(["run", "--strict-omx-native", "--verify-error-policy", "skip", "--verify-fallback-mode", "mock"])
        self.assertTrue(args.strict_omx_native)
        self.assertEqual(args.verify_error_policy, "skip")
        self.assertEqual(args.verify_fallback_mode, "mock")
        args = parser.parse_args(["run", "--require-live-verification"])
        self.assertTrue(args.require_live_verification)
        args = parser.parse_args(["audit-reproducibility", "--require-live-verification"])
        self.assertTrue(args.require_live_verification)

    def test_direct_discover_papers_model_mode_still_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "idea.md").write_text("idea\n", encoding="utf-8")
            (root / "experimental_log.md").write_text("# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\\begin{document}\\section{Introduction}\\section{Related Work}\\section{Method}\\end{document}\n", encoding="utf-8")
            (root / "guidelines.md").write_text("guidelines\n", encoding="utf-8")
            (root / "figs").mkdir()
            create_session(
                root,
                InputBundle(
                    idea_path=str(root / "idea.md"),
                    experimental_log_path=str(root / "experimental_log.md"),
                    template_path=str(root / "template.tex"),
                    guidelines_path=str(root / "guidelines.md"),
                    figures_dir=str(root / "figs"),
                    cutoff_date="2024-11-01",
                ),
            )
            generate_outline(root, MockProvider())
            path = discover_papers(root, MockProvider(), mode="model")
            self.assertTrue(Path(path).exists())
            state = load_session(root)
            self.assertEqual(state.latest_discovery_mode, "model")
            self.assertEqual(state.current_phase, "literature_review")

    def test_direct_discover_papers_search_grounded_mode_works_with_mock_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "idea.md").write_text("idea\n", encoding="utf-8")
            (root / "experimental_log.md").write_text("# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\\begin{document}\\section{Introduction}\\section{Related Work}\\section{Method}\\end{document}\n", encoding="utf-8")
            (root / "guidelines.md").write_text("guidelines\n", encoding="utf-8")
            (root / "figs").mkdir()
            create_session(
                root,
                InputBundle(
                    idea_path=str(root / "idea.md"),
                    experimental_log_path=str(root / "experimental_log.md"),
                    template_path=str(root / "template.tex"),
                    guidelines_path=str(root / "guidelines.md"),
                    figures_dir=str(root / "figs"),
                    cutoff_date="2024-11-01",
                ),
            )
            generate_outline(root, MockProvider())
            path = discover_papers(root, MockProvider(), mode="search-grounded")
            self.assertTrue(Path(path).exists())
            state = load_session(root)
            self.assertEqual(state.latest_discovery_mode, "search-grounded")

    def test_live_verification_merges_instead_of_erasing_curated_bibtex_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "idea.md").write_text("idea\n", encoding="utf-8")
            (root / "experimental_log.md").write_text("# Experimental Log\n", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\\begin{document}\\end{document}\n", encoding="utf-8")
            (root / "guidelines.md").write_text("guidelines\n", encoding="utf-8")
            (root / "figs").mkdir()
            create_session(
                root,
                InputBundle(
                    idea_path=str(root / "idea.md"),
                    experimental_log_path=str(root / "experimental_log.md"),
                    template_path=str(root / "template.tex"),
                    guidelines_path=str(root / "guidelines.md"),
                    figures_dir=str(root / "figs"),
                    cutoff_date="2026-01-01",
                ),
            )
            seed_path = root / "refs.bib"
            seed_path.write_text(
                "@article{PriorAlpha,\n"
                "  title = {Alpha Protected Channels},\n"
                "  author = {Ada Author},\n"
                "  year = {2020},\n"
                "  journal = {Journal of Tests}\n"
                "}\n\n"
                "@misc{PriorBeta,\n"
                "  title = {Beta Standard Document},\n"
                "  author = {Standards Body},\n"
                "  year = {2021},\n"
                "  url = {https://example.test/beta}\n"
                "}\n",
                encoding="utf-8",
            )
            import_prior_work(root, seed_file=seed_path, source="manual_bibtex")

            def fake_verify(title: str, **kwargs):
                if title == "Alpha Protected Channels":
                    paper = VerifiedPaper(
                        paper_id="S2:alpha",
                        title=title,
                        year=2020,
                        publication_date="2020-01-01",
                        venue="Verified Venue",
                        abstract="Live metadata.",
                        authors=["Ada Author"],
                        citation_count=7,
                        external_ids={},
                        url="https://example.test/alpha-live",
                        origin="semantic_scholar",
                        matched_query=title,
                        title_match_ratio=100.0,
                    )
                    paper.bibtex_key = "LiveAlpha"
                    return paper
                return None

            with patch("paperorchestra.pipeline.verify_candidate_title", side_effect=fake_verify):
                verify_papers(root, mode="live", on_error="skip")
            build_bib(root)

            state = load_session(root)
            citation_map = read_json(state.artifacts.citation_map_json)
            registry = read_json(state.artifacts.citation_registry_json)
            bib = Path(state.artifacts.references_bib).read_text(encoding="utf-8")

            self.assertIn("PriorAlpha", citation_map)
            self.assertIn("LiveAlpha", citation_map)
            self.assertIn("PriorBeta", citation_map)
            self.assertEqual(citation_map["PriorAlpha"]["venue"], "Verified Venue")
            self.assertEqual(len(registry), 2)
            self.assertIn("{PriorAlpha,", bib)
            self.assertIn("{LiveAlpha,", bib)
            self.assertIn("{PriorBeta,", bib)

    def test_experimental_log_search_queries_extract_baselines_and_datasets(self) -> None:
        text = (
            "# Experimental Log\n\n"
            "## 1. Experimental Setup\n"
            "* **Datasets / Benchmarks:** PaperWritingBench (200 papers)\n"
            "* **Baselines:** Single Agent, AI Scientist-v2\n"
            "* **Evaluation Metrics:** Citation F1, Literature Review Quality\n"
        )
        queries = _experimental_log_search_queries(text)
        self.assertIn("PaperWritingBench (200 papers)", queries)
        self.assertIn("Single Agent", queries)
        self.assertIn("AI Scientist-v2", queries)
        self.assertIn("Citation F1", queries)


if __name__ == "__main__":
    unittest.main()
