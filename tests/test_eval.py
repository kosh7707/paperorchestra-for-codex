from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main
from paperorchestra.eval import (
    build_reference_benchmark_case,
    build_generated_citation_titles,
    compute_partitioned_citation_coverage,
    parse_reported_margin_ranges,
    write_reference_benchmark_case,
)
from paperorchestra.mcp_server import (
    tool_build_generated_citation_titles,
    tool_build_citation_partition_request,
    tool_build_review_gate_comparison,
    tool_build_reference_case_partition_scaffold,
    tool_build_reference_benchmark_case,
    tool_compare_reference_case_citation_coverage,
    tool_compare_partitioned_citation_coverage,
    tool_build_session_eval_summary,
    tool_compare_reference_case,
)
from paperorchestra.models import InputBundle
from paperorchestra.providers import MockProvider
from paperorchestra.pipeline import run_pipeline
from paperorchestra.session import create_session, load_session


def _latest_review_path(root: Path) -> Path:
    state = load_session(root)
    return Path(state.artifacts.latest_review_json or root / "missing.json")


class EvalScaffoldTests(unittest.TestCase):
    def test_parse_reported_margin_ranges_extracts_expected_metrics(self) -> None:
        text = (
            "PaperOrchestra achieved absolute win rate margins of 50%–68% in literature review quality, "
            "and 14%–38% in overall manuscript quality."
        )
        payload = parse_reported_margin_ranges(text)
        self.assertEqual(payload["literature_review_quality"]["min"], 50.0)
        self.assertEqual(payload["literature_review_quality"]["max"], 68.0)
        self.assertEqual(payload["overall_manuscript_quality"]["min"], 14.0)
        self.assertEqual(payload["overall_manuscript_quality"]["max"], 38.0)
        self.assertEqual(payload["literature_review_quality"]["source_excerpt"], "literature review quality")

    def test_build_reference_benchmark_case_packages_reference_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "seed_answers.json").write_text(
                json.dumps(
                    {
                        "baselines": ["Single Agent", "AI Scientist-v2"],
                        "datasets_or_benchmarks": ["PaperWritingBench"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (root / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (root / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")

            payload = build_reference_benchmark_case(root)
            self.assertEqual(payload["case_id"], "paperorchestra-reference")
            self.assertEqual(payload["source_type"], "paper-derived")
            self.assertTrue(payload["comparability"]["baseline_names_present"])
            self.assertTrue(payload["comparability"]["reported_margins_present"])
            self.assertIn("literature_review_quality", payload["reported_margin_ranges"])

    def test_write_reference_benchmark_case_writes_json_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (root / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (root / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (root / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")

            out_path = write_reference_benchmark_case(root, root / "benchmark_case.json", source_pdf=root / "paper.pdf")
            self.assertTrue(out_path.exists())
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["inputs"]["seed_answers_path"], str(root / "seed_answers.json"))

    def test_partition_request_and_partitioned_coverage_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_text_file = root / "paper.txt"
            refs_file = root / "refs.json"
            partition_file = root / "partition.json"
            generated_titles_file = root / "generated_titles.json"
            paper_text_file.write_text("Demo paper body", encoding="utf-8")
            refs = [{"title": "Alpha Baseline"}, {"title": "Beta Dataset"}, {"title": "Gamma Background"}]
            refs_file.write_text(json.dumps(refs), encoding="utf-8")
            partition_file.write_text(json.dumps({"1": "P0", "2": "P0", "3": "P1"}), encoding="utf-8")
            generated_titles_file.write_text(json.dumps(["Alpha Baseline", "Gamma Background"]), encoding="utf-8")

            partition_request_path = root / "partition_request.json"
            coverage_path = root / "coverage.json"
            req_path = tool_build_citation_partition_request(
                {"paper_text_file": str(paper_text_file), "references_json": str(refs_file), "output_path": str(partition_request_path)}
            )["content"][0]["text"]
            cov_path = tool_compare_partitioned_citation_coverage(
                {
                    "references_json": str(refs_file),
                    "partition_json": str(partition_file),
                    "generated_titles_json": str(generated_titles_file),
                    "output_path": str(coverage_path),
                }
            )["content"][0]["text"]
            self.assertIn(str(partition_request_path), req_path)
            self.assertIn(str(coverage_path), cov_path)
            partition_request = json.loads(partition_request_path.read_text(encoding="utf-8"))
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            self.assertEqual(partition_request["reference_count"], 3)
            self.assertEqual(coverage["partition_coverage"]["P0"]["matched"], 1)
            self.assertEqual(coverage["partition_coverage"]["P1"]["matched"], 1)

    def test_cli_build_reference_benchmark_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (root / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (root / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (root / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            out = root / "custom-benchmark.json"
            code = cli_main(["build-reference-benchmark-case", "--reference-dir", str(root), "--output", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())

    def test_mcp_build_reference_benchmark_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (root / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (root / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (root / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (root / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            out = root / "mcp-benchmark.json"
            payload = json.loads(
                tool_build_reference_benchmark_case(
                    {"reference_dir": str(root), "output_path": str(out)}
                )["content"][0]["text"]
            )
            self.assertEqual(payload["path"], str(out))
            self.assertTrue(out.exists())

    def test_build_session_eval_summary_and_reference_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            summary_path = root / "session_eval_summary.json"
            comparison_path = root / "reference_comparison.json"
            summary_payload = json.loads(
                tool_build_session_eval_summary({"cwd": str(root), "output_path": str(summary_path)})["content"][0]["text"]
            )
            review_gate_path = root / "review_gate_comparison.json"
            review_gate_payload = json.loads(
                tool_build_review_gate_comparison({"cwd": str(root), "output_path": str(review_gate_path)})["content"][0]["text"]
            )
            comparison_payload = json.loads(
                tool_compare_reference_case(
                    {"cwd": str(root), "reference_case": str(reference_case), "output_path": str(comparison_path)}
                )["content"][0]["text"]
            )
            self.assertEqual(summary_payload["path"], str(summary_path))
            self.assertEqual(review_gate_payload["path"], str(review_gate_path))
            self.assertEqual(comparison_payload["path"], str(comparison_path))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            review_gate = json.loads(review_gate_path.read_text(encoding="utf-8"))
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["current_phase"], "draft_complete")
            self.assertTrue(summary["verified_citation_count"] > 0)
            self.assertTrue(summary["candidate_count"] > 0)
            self.assertEqual(summary["candidate_discovery_sources"], [])
            self.assertEqual(summary["candidate_discovery_source_counts"], {})
            self.assertEqual(summary["candidate_discovery_mode"], "model")
            self.assertFalse(summary["search_grounded_required_sources_present"])
            self.assertEqual(review_gate["comparability_status"], "implemented")
            self.assertEqual(review_gate["overlap_count"], 6)
            self.assertEqual(review_gate["missing_citation_statistics_keys"], [])
            self.assertEqual(review_gate["missing_summary_keys"], [])
            self.assertGreater(review_gate["questions_count"], 0)
            self.assertEqual(review_gate["anti_inflation_violations"], [])
            self.assertEqual(comparison["reference_case_id"], "paperorchestra-reference")
            self.assertTrue(comparison["comparability"]["session_review_available"])
            self.assertTrue(comparison["comparability"]["search_grounded_sources_present"] is False)
            self.assertEqual(comparison["expected_search_grounded_sources"], ["semantic_scholar", "openalex"])
            self.assertIn("coverage_and_completeness", comparison["expected_review_axes"])
            self.assertEqual(comparison["comparability"]["agentreview_axis_overlap_count"], 6)
            self.assertEqual(comparison["comparability"]["agentreview_axis_missing"], [])
            self.assertEqual(comparison["review_gate_comparison"]["comparability_status"], "implemented")
            self.assertIn("partition_coverage", comparison["reference_case_partitioned_citation_coverage"]["coverage"])
            self.assertTrue(comparison["generated_citation_titles"]["count"] > 0)
            generated_path = root / "generated_citation_titles.json"
            gen_payload = json.loads(
                tool_build_generated_citation_titles({"cwd": str(root), "output_path": str(generated_path)})["content"][0]["text"]
            )
            self.assertEqual(gen_payload["path"], str(generated_path))
            generated = json.loads(generated_path.read_text(encoding="utf-8"))
            self.assertTrue(generated["generated_titles"])

    def test_cli_build_session_eval_summary_and_compare_reference_case(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                summary_path = root / "cli-session-eval-summary.json"
                comparison_path = root / "cli-reference-comparison.json"
                self.assertEqual(cli_main(["build-session-eval-summary", "--output", str(summary_path)]), 0)
                self.assertEqual(
                    cli_main(
                        [
                            "compare-reference-case",
                            "--reference-case",
                            str(reference_case),
                            "--output",
                            str(comparison_path),
                        ]
                    ),
                    0,
                )
            finally:
                os.chdir(old_cwd)

            self.assertTrue(summary_path.exists())
            self.assertTrue(comparison_path.exists())
            review_gate_path = root / "cli-review-gate-comparison.json"
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(cli_main(["build-review-gate-comparison", "--output", str(review_gate_path)]), 0)
            finally:
                os.chdir(old_cwd)
            self.assertTrue(review_gate_path.exists())

    def test_cli_and_mcp_partition_scaffold_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_text_file = root / "paper.txt"
            refs_file = root / "refs.json"
            partition_file = root / "partition.json"
            generated_titles_file = root / "generated_titles.json"
            paper_text_file.write_text("Demo paper body", encoding="utf-8")
            refs = [{"title": "Alpha Baseline"}, {"title": "Beta Dataset"}, {"title": "Gamma Background"}]
            refs_file.write_text(json.dumps(refs), encoding="utf-8")
            partition_file.write_text(json.dumps({"1": "P0", "2": "P0", "3": "P1"}), encoding="utf-8")
            generated_titles_file.write_text(json.dumps(["Alpha Baseline", "Gamma Background"]), encoding="utf-8")

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                cli_request = root / "cli_partition_request.json"
                cli_coverage = root / "cli_partition_coverage.json"
                self.assertEqual(
                    cli_main(
                        [
                            "build-citation-partition-request",
                            "--paper-text-file",
                            str(paper_text_file),
                            "--references-json",
                            str(refs_file),
                            "--output",
                            str(cli_request),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli_main(
                        [
                            "compare-partitioned-citation-coverage",
                            "--references-json",
                            str(refs_file),
                            "--partition-json",
                            str(partition_file),
                            "--generated-titles-json",
                            str(generated_titles_file),
                            "--output",
                            str(cli_coverage),
                        ]
                    ),
                    0,
                )
            finally:
                os.chdir(old_cwd)

            self.assertTrue(cli_request.exists())
            self.assertTrue(cli_coverage.exists())

    def test_reference_case_partition_scaffold_and_coverage_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps({"baselines": ["AutoSurvey2", "LiRA"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            scaffold_path = root / "reference_case_partition_scaffold.json"
            coverage_path = root / "reference_case_partitioned_citation_coverage.json"
            scaffold_payload = json.loads(
                tool_build_reference_case_partition_scaffold(
                    {"reference_case": str(reference_case), "output_path": str(scaffold_path)}
                )["content"][0]["text"]
            )
            coverage_payload = json.loads(
                tool_compare_reference_case_citation_coverage(
                    {"cwd": str(root), "reference_case": str(reference_case), "output_path": str(coverage_path)}
                )["content"][0]["text"]
            )
            self.assertEqual(scaffold_payload["path"], str(scaffold_path))
            self.assertEqual(coverage_payload["path"], str(coverage_path))
            scaffold = json.loads(scaffold_path.read_text(encoding="utf-8"))
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            self.assertEqual(scaffold["partition_map"]["1"], "P0")
            self.assertEqual(coverage["coverage"]["partition_coverage"]["P0"]["matched"], 2)

    def test_cli_and_mcp_reference_case_partition_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps({"baselines": ["AutoSurvey2", "LiRA"], "datasets_or_benchmarks": ["PaperWritingBench"]}),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                cli_scaffold = root / "cli_reference_case_partition_scaffold.json"
                cli_coverage = root / "cli_reference_case_partitioned_citation_coverage.json"
                self.assertEqual(
                    cli_main(
                        [
                            "build-reference-case-partition-scaffold",
                            "--reference-case",
                            str(reference_case),
                            "--output",
                            str(cli_scaffold),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli_main(
                        [
                            "compare-reference-case-citation-coverage",
                            "--reference-case",
                            str(reference_case),
                            "--output",
                            str(cli_coverage),
                        ]
                    ),
                    0,
                )
            finally:
                os.chdir(old_cwd)

            self.assertTrue(cli_scaffold.exists())
            self.assertTrue(cli_coverage.exists())

            mcp_scaffold = root / "mcp_reference_case_partition_scaffold.json"
            mcp_coverage = root / "mcp_reference_case_partitioned_citation_coverage.json"
            scaffold_payload = json.loads(
                tool_build_reference_case_partition_scaffold(
                    {"reference_case": str(reference_case), "output_path": str(mcp_scaffold)}
                )["content"][0]["text"]
            )
            coverage_payload = json.loads(
                tool_compare_reference_case_citation_coverage(
                    {"cwd": str(root), "reference_case": str(reference_case), "output_path": str(mcp_coverage)}
                )["content"][0]["text"]
            )
            self.assertEqual(scaffold_payload["path"], str(mcp_scaffold))
            self.assertEqual(coverage_payload["path"], str(mcp_coverage))
            coverage = json.loads(mcp_coverage.read_text(encoding="utf-8"))
            self.assertEqual(coverage["coverage"]["partition_coverage"]["P0"]["matched"], 2)


    def test_reference_comparison_only_marks_search_grounded_when_mode_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            # Force sources that could be mistaken for grounded search, without changing the true discovery mode.
            candidate_path = Path(root / ".paper-orchestra" / "runs")
            session_dirs = sorted(candidate_path.iterdir())
            state_dir = session_dirs[0]
            candidates_file = state_dir / "artifacts" / "candidate_papers.json"
            candidates = json.loads(candidates_file.read_text(encoding="utf-8"))
            for bucket in ("macro_candidates", "micro_candidates"):
                for item in candidates.get(bucket, []):
                    item["discovery_source"] = "semantic_scholar"
            candidates_file.write_text(json.dumps(candidates), encoding="utf-8")

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}), encoding="utf-8")
            (reference_dir / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            comparison_path = root / "reference_comparison.json"
            tool_compare_reference_case({"cwd": str(root), "reference_case": str(reference_case), "output_path": str(comparison_path)})
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            self.assertFalse(comparison["comparability"]["search_grounded_sources_present"])

    def test_reference_comparison_marks_search_grounded_when_mode_is_search_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            with patch(
                "paperorchestra.pipeline.build_search_grounded_candidates",
                return_value=(
                    {
                        "macro_candidates": [
                            {
                                "title_guess": "Alpha Paper",
                                "why_relevant": "grounded macro",
                                "origin_query": "macro",
                                "role_guess": "macro",
                                "discovery_source": "semantic_scholar",
                            }
                        ],
                        "micro_candidates": [
                            {
                                "title_guess": "Beta Paper",
                                "why_relevant": "grounded micro",
                                "origin_query": "micro",
                                "role_guess": "micro",
                                "discovery_source": "openalex",
                            }
                        ],
                    },
                    ["grounded search mocked"],
                ),
            ):
                run_pipeline(
                    root,
                    provider=MockProvider(),
                    discovery_mode="search-grounded",
                    verify_mode="mock",
                    refine_iterations=1,
                    compile_paper=False,
                )
            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(json.dumps({"baselines": ["Single Agent"], "datasets_or_benchmarks": ["PaperWritingBench"]}), encoding="utf-8")
            (reference_dir / "results.md").write_text("Absolute win-rate margins of 50%–68% in literature review quality.", encoding="utf-8")
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            reference_case = reference_dir / "benchmark_case.json"
            write_reference_benchmark_case(reference_dir, reference_case)

            comparison_path = root / "reference_comparison.json"
            tool_compare_reference_case({"cwd": str(root), "reference_case": str(reference_case), "output_path": str(comparison_path)})
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            self.assertTrue(comparison["comparability"]["search_grounded_sources_present"])
            self.assertFalse(comparison["comparability"]["search_grounded_attempted_sources_present"])
            summary = json.loads((root / "reference_comparison.json").read_text(encoding="utf-8"))["session_summary"]
            self.assertEqual(summary["candidate_discovery_mode"], "search-grounded")
            self.assertTrue(summary["search_grounded_required_sources_present"])
            self.assertFalse(summary["search_grounded_attempted_required_sources_present"])
            self.assertEqual(summary["candidate_discovery_source_counts"], {"semantic_scholar": 1, "openalex": 1})

    def test_session_eval_summary_tracks_attempted_grounded_sources_from_lane_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            state = load_session(root)
            runs_dir = root / ".paper-orchestra" / "runs" / state.session_id / "artifacts"
            candidates = json.loads((runs_dir / "candidate_papers.json").read_text(encoding="utf-8"))
            candidates["macro_candidates"][0]["discovery_source"] = "session_seed"
            candidates["macro_candidates"][0]["discovery_sources"] = ["session_seed"]
            (runs_dir / "candidate_papers.json").write_text(json.dumps(candidates), encoding="utf-8")
            lane_manifest = {
                "notes": [
                    "Semantic Scholar grounded query completed: Single Agent",
                    "OpenAlex grounded query completed: Single Agent",
                    "Exact grounded seed preserved without matching live result: Single Agent",
                ]
            }
            (runs_dir / "lane-manifest.literature.json").write_text(json.dumps(lane_manifest), encoding="utf-8")
            state.latest_discovery_mode = "search-grounded"
            from paperorchestra.session import save_session
            save_session(root, state)

            summary_path = root / "attempted-summary.json"
            tool_build_session_eval_summary({"cwd": str(root), "output_path": str(summary_path)})
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["candidate_discovery_sources"], ["session_seed"])
            self.assertEqual(summary["candidate_discovery_attempted_sources"], ["semantic_scholar", "openalex"])
            self.assertFalse(summary["search_grounded_required_sources_present"])
            self.assertTrue(summary["search_grounded_attempted_required_sources_present"])

    def test_review_gate_comparison_requires_expected_detail_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=1, compile_paper=False)
            review_path = _latest_review_path(root)
            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
            review_payload["citation_statistics"].pop("notes", None)
            review_payload["summary"].pop("top_improvements", None)
            review_payload["questions"] = []
            review_path.write_text(json.dumps(review_payload), encoding="utf-8")
            review_gate_path = root / "review_gate_comparison.json"
            payload = json.loads(tool_build_review_gate_comparison({"cwd": str(root), "output_path": str(review_gate_path)})["content"][0]["text"])
            self.assertEqual(payload["path"], str(review_gate_path))
            review_gate = json.loads(review_gate_path.read_text(encoding="utf-8"))
            self.assertEqual(review_gate["comparability_status"], "partial")
            self.assertEqual(review_gate["missing_citation_statistics_keys"], ["notes"])
            self.assertEqual(review_gate["missing_summary_keys"], ["top_improvements"])
            self.assertEqual(review_gate["questions_count"], 0)

    def test_review_gate_comparison_flags_anti_inflation_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n\\section{Introduction}\n\\section{Related Work}\n\\section{Method}\n\\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
            }.items():
                (root / name).write_text(content, encoding="utf-8")
            (root / "figures").mkdir()
            create_session(
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
            run_pipeline(root, provider=MockProvider(), discovery_mode="model", verify_mode="mock", refine_iterations=1, compile_paper=False)
            review_path = _latest_review_path(root)
            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
            review_payload["overall_score"] = 80
            review_payload["axis_scores"]["coverage_and_completeness"]["score"] = 45
            review_path.write_text(json.dumps(review_payload), encoding="utf-8")
            review_gate_path = root / "review_gate_comparison.json"
            json.loads(tool_build_review_gate_comparison({"cwd": str(root), "output_path": str(review_gate_path)})["content"][0]["text"])
            review_gate = json.loads(review_gate_path.read_text(encoding="utf-8"))
            self.assertIn("overall_score_above_75_with_sub50_axis", review_gate["anti_inflation_violations"])
            self.assertEqual(review_gate["comparability_status"], "partial")

    def test_generated_citation_titles_supports_common_cite_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in {
                "idea.md": "## Problem Statement\nDemo\n",
                "experimental_log.md": "# Experimental Log\n\n## 1. Experimental Setup\n* **Datasets:** DemoSet\n",
                "template.tex": r"\documentclass{article}\n\begin{document}\n\section{Introduction}\n\end{document}\n",
                "guidelines.md": "Target venue: DemoConf\n",
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
            run_dir = root / ".paper-orchestra" / "runs" / state.session_id / "artifacts"
            paper_path = run_dir / "paper.full.tex"
            citation_map_path = run_dir / "citation_map.json"
            paper_path.write_text(
                r"\section{Intro} See \citep{alpha,beta} and \citet[Sec.~2]{gamma}. Reusing \cite{alpha}.\n",
                encoding="utf-8",
            )
            citation_map_path.write_text(
                json.dumps(
                    {
                        "alpha": {"title": "Alpha Paper", "paper_id": "a1"},
                        "beta": {"title": "Beta Paper", "paper_id": "b1"},
                        "gamma": {"title": "Gamma Paper", "paper_id": "g1"},
                    }
                ),
                encoding="utf-8",
            )
            state.artifacts.paper_full_tex = str(paper_path)
            state.artifacts.citation_map_json = str(citation_map_path)
            from paperorchestra.session import save_session
            save_session(root, state)

            payload = build_generated_citation_titles(root)
            self.assertEqual(payload["cited_keys"], ["alpha", "beta", "gamma"])
            self.assertEqual(payload["generated_titles"], ["Alpha Paper", "Beta Paper", "Gamma Paper"])
            self.assertEqual(len(payload["resolved_entries"]), 3)

    def test_partitioned_citation_coverage_supports_fuzzy_matching_without_double_counting(self) -> None:
        refs = [
            {"title": "AutoSurvey 2: Querying and Aggregating Sources"},
            {"title": "LiRA: Literature Review Assistant"},
            {"title": "Background Methods for Writing"},
        ]
        partition = {"1": "P0", "2": "P0", "3": "P1"}
        generated_titles = [
            "AutoSurvey2",
            "LiRA",
            "AutoSurvey2",
        ]

        coverage = compute_partitioned_citation_coverage(refs, partition, generated_titles)
        self.assertEqual(coverage["partition_coverage"]["P0"]["matched"], 2)
        self.assertEqual(coverage["partition_coverage"]["P1"]["matched"], 0)
        self.assertEqual(coverage["matched_generated_title_count"], 2)
        self.assertEqual(coverage["generated_title_count"], 3)
        self.assertAlmostEqual(coverage["generated_precision"], 0.6667, places=4)
        match_types = {pair["match_type"] for pair in coverage["matched_pairs"]}
        self.assertIn("compact", match_types)
        self.assertIn("AutoSurvey2", coverage["unmatched_generated_titles"])

    def test_partitioned_citation_coverage_avoids_short_compact_false_positive(self) -> None:
        coverage = compute_partitioned_citation_coverage(
            [{"title": "Single Agent"}],
            {"1": "P0"},
            ["Single-Agent Pixantrone as a Bridge to Autologous Stem Cell Transplantation"],
        )
        self.assertEqual(coverage["partition_coverage"]["P0"]["matched"], 0)
        self.assertEqual(coverage["matched_generated_title_count"], 0)


if __name__ == "__main__":
    unittest.main()
