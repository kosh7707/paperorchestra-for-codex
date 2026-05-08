from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.critics import extract_cited_sentences
from paperorchestra.io_utils import extract_json, extract_latex
from paperorchestra.validator import (
    build_figure_placement_review,
    canonicalize_citation_keys,
    extract_decimal_like_tokens,
    extract_citation_keys,
    validate_manuscript,
)
from paperorchestra.pipeline import validate_outline, validate_paper_contract
class JsonExtractionTests(unittest.TestCase):
    def test_extract_json_from_fenced_block(self) -> None:
        payload = extract_json("before\n```json\n{\"a\": 1}\n```\nafter")
        self.assertEqual(payload["a"], 1)

    def test_extract_json_repairs_llm_latex_backslashes_inside_strings(self) -> None:
        payload = extract_json(
            '{"items":[{"reasoning":"The construction \\(B_0 := n_1 || 0^{31} || 1\\) is cited."}]}'
        )
        self.assertEqual(payload["items"][0]["reasoning"], "The construction \\(B_0 := n_1 || 0^{31} || 1\\) is cited.")

    def test_extract_latex_from_fenced_block(self) -> None:
        latex = extract_latex("```latex\n\\documentclass{article}\n\\begin{document}Hi\\end{document}\n```")
        self.assertIn("\\documentclass{article}", latex)

class OutlineValidationTests(unittest.TestCase):
    def test_validate_outline_accepts_required_contract(self) -> None:
        payload = {
            "plotting_plan": [
                {
                    "figure_id": "fig_example",
                    "title": "Example",
                    "plot_type": "diagram",
                    "data_source": "both",
                    "objective": "Explain the system.",
                    "aspect_ratio": "16:9",
                }
            ],
            "intro_related_work_plan": {},
            "section_plan": [],
        }
        validate_outline(payload)

    def test_validate_paper_contract_detects_multiple_fidelity_issues(self) -> None:
        issues = validate_paper_contract(
            "\\section{Intro} Unsupported result 99.9 with \\cite{alpha}. It outperforms prior work.",
            citation_map={"alpha": {}, "beta": {}},
            figures_dir=None,
            plot_manifest={"figures": [{"figure_id": "fig_framework_overview", "title": "Framework overview", "caption": "Overview"}]},
            experimental_log_text="Recorded grounded value 44.3 only.",
        )
        self.assertTrue(any("Insufficient citation coverage" in issue for issue in issues))
        self.assertTrue(any("Plot-plan figures" in issue for issue in issues))
        self.assertTrue(any("not grounded in the experimental log" in issue for issue in issues))
        self.assertTrue(any("comparative claims" in issue for issue in issues))

    def test_citation_extraction_supports_common_latex_cite_commands(self) -> None:
        latex = (
            "\\cite{Alpha, Beta} "
            "\\citep[see][p. 4]{Gamma} "
            "\\citet*{Delta} "
            "\\parencite{Epsilon} "
            "\\textcite{Zeta}"
        )
        self.assertEqual(extract_citation_keys(latex), {"Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"})

    def test_canonicalize_citation_keys_preserves_cite_command_forms(self) -> None:
        latex, replacements = canonicalize_citation_keys(
            "\\citep[see][p. 4]{RFC9001} and \\textcite{TLS13}.",
            {"Rfc9001": {}, "Tls13": {}},
        )
        self.assertIn("\\citep[see][p. 4]{Rfc9001}", latex)
        self.assertIn("\\textcite{Tls13}", latex)
        self.assertEqual(replacements, {"RFC9001": "Rfc9001", "TLS13": "Tls13"})

    def test_citation_coverage_scales_less_aggressively_for_large_bibliographies(self) -> None:
        citation_map = {f"k{i}": {} for i in range(59)}
        cited = ",".join(f"k{i}" for i in range(49))
        issues = validate_manuscript(
            f"\\section{{Intro}} Supported framing with \\\\cite{{{cited}}}.",
            citation_map=citation_map,
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertFalse(any(issue.code == "citation_coverage_insufficient" for issue in issues))

    def test_citation_coverage_requires_about_seventy_percent_for_very_large_bibliographies(self) -> None:
        citation_map = {f"k{i}": {} for i in range(59)}
        cited = ",".join(f"k{i}" for i in range(40))
        issues = validate_manuscript(
            f"\\section{{Intro}} Supported framing with \\\\cite{{{cited}}}.",
            citation_map=citation_map,
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "citation_coverage_insufficient" for issue in issues))

    def test_validate_manuscript_preserves_warning_severity(self) -> None:
        issues = validate_manuscript(
            "\\section{Intro} It outperforms prior work while citing \\cite{alpha,beta}.",
            citation_map={"alpha": {}, "beta": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="No comparative claims here.",
        )
        self.assertTrue(any(issue.severity == "warning" for issue in issues))

    def test_validate_manuscript_rejects_prompt_meta_leakage(self) -> None:
        issues = validate_manuscript(
            "\\section{Intro} Caption intent: internal generation objective with \\cite{alpha}.",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_validate_manuscript_ignores_prompt_meta_words_in_latex_comments(self) -> None:
        issues = validate_manuscript(
            "\\begin{abstract}\n% PaperOrchestra writes this.\n\\end{abstract}\n"
            "\\section{Intro} The artifact workflow is evaluated as a bounded drafting aid. \\cite{alpha}",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertFalse(any(issue.code == "prompt_meta_leakage" for issue in issues))

    def test_validate_manuscript_rejects_generic_boundary_note_sections(self) -> None:
        issues = validate_manuscript(
            r"\section{Claim Boundaries for the Example Draft} Operator note with \cite{alpha}.",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_validate_manuscript_allows_scholarly_claim_boundary_phrase(self) -> None:
        issues = validate_manuscript(
            (
                "\\section{Security Analysis}\n"
                "\\subsection{Assumptions, Composition Rationale, and Claim Boundaries}\n"
                "The two bounds isolate the assumptions under which the paper's claims are evaluated. "
                "\\cite{alpha}"
            ),
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertFalse(any(issue.code == "prompt_meta_leakage" for issue in issues))

    def test_expected_section_titles_accept_latex_section_wrappers_from_planners(self) -> None:
        issues = validate_manuscript(
            "\\section{Proposed Method}\nThe construction uses streaming mode, authentication, and run-token material. \\cite{alpha}\n",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=["\\section{Proposed Method}"],
        )

        self.assertFalse(any(issue.code == "expected_section_missing" for issue in issues))

    def test_expected_section_substance_ignores_abstract_environment_from_planners(self) -> None:
        issues = validate_manuscript(
            (
                "\\begin{abstract}\n"
                "This abstract summarizes the paper contribution.\n"
                "\\end{abstract}\n"
                "\\section{Introduction}\n"
                "This introduction has enough substantive prose to satisfy the expected section check."
            ),
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=[r"\begin{abstract}", r"\section{Introduction}"],
        )

        self.assertFalse(any(issue.code == "expected_section_missing" for issue in issues))

    def test_validate_manuscript_rejects_process_leakage_phrases(self) -> None:
        issues = validate_manuscript(
            (
                "\\section{Results} The revised manuscript uses the benchmark packet and "
                "notes that the figures directory is empty in this packet. \\cite{alpha}"
            ),
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_validate_manuscript_rejects_source_boundary_meta_leakage(self) -> None:
        issues = validate_manuscript(
            (
                "\\section{Intro} Within the supplied source boundary, this result is limited to the "
                "provided material and does not add an external claim. \\cite{alpha}"
            ),
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_validate_manuscript_rejects_source_grounded_control_prose(self) -> None:
        issues = validate_manuscript(
            (
                "\\section{Discussion} The draft must preserve source-grounded limitations, "
                "assumptions, and claim boundaries without broadening them. \\cite{alpha}"
            ),
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_validate_manuscript_rejects_benchmark_narrative_control_prose(self) -> None:
        issues = validate_manuscript(
            (
                "\\section{Results} The benchmark narrative must report only measurements "
                "and comparisons grounded in the experimental log. \\cite{alpha}"
            ),
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
        )
        self.assertTrue(any(issue.code == "prompt_meta_leakage" and issue.severity == "error" for issue in issues))

    def test_cited_sentence_extraction_ignores_preamble_and_macros(self) -> None:
        latex = (
            "\\documentclass{article}\n"
            "\\newcommand{\\METHODX}{\\mathsf{MethodX}}\n"
            "\\begin{document}\n"
            "\\title{Example}\\maketitle\n"
            "\\begin{abstract}Transport protected-channels are standardized for records \\cite{RFC8446}.\\end{abstract}\n"
            "\\section{Background}\n"
            "Prior run-token-based protected-channel work motivates the model \\cite{Rogaway2002}.\n"
            "\\bibliographystyle{plain}\\bibliography{references}\n"
            "\\end{document}\n"
        )

        sentences = extract_cited_sentences(latex)

        self.assertEqual(len(sentences), 2)
        self.assertTrue(sentences[0].startswith("Transport protected-channels"))
        self.assertNotIn("\\documentclass", sentences[0])
        self.assertNotIn("\\newcommand", " ".join(sentences))
        self.assertIn("\\cite{RFC8446}", sentences[0])

    def test_numeric_grounding_normalizes_multiplier_suffixes(self) -> None:
        self.assertIn("2.54", extract_decimal_like_tokens("A 2.54x speedup and 3.10\\times gain."))
        issues = validate_manuscript(
            "Grounded result is 2.54$\\times$ while citing \\cite{alpha}.",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="Measured 2.54x speedup.",
        )
        self.assertFalse(any(issue.code == "numeric_grounding_mismatch" for issue in issues))

    def test_numeric_grounding_ignores_arraystretch_layout_numbers(self) -> None:
        issues = validate_manuscript(
            "\\renewcommand{\\arraystretch}{1.15}\n\\section{Intro} Grounded result with \\cite{alpha}.",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="No decimal measurements recorded here.",
        )
        self.assertFalse(any(issue.code == "numeric_grounding_mismatch" for issue in issues))

    def test_numeric_grounding_ignores_minipage_layout_numbers(self) -> None:
        issues = validate_manuscript(
            "\\begin{minipage}{0.97\\columnwidth}\nLayout scaffold only.\n\\end{minipage}\n\\section{Intro} Grounded result with \\cite{alpha}.",
            citation_map={"alpha": {}},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="No decimal measurements recorded here.",
        )
        self.assertFalse(any(issue.code == "numeric_grounding_mismatch" for issue in issues))

    def test_numeric_grounding_ignores_tabular_column_width_layout_numbers(self) -> None:
        issues = validate_manuscript(
            "\\section{Method}\\begin{tabular}{p{0.20\\columnwidth}p{0.70\\columnwidth}}A&B\\\\\\end{tabular}",
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="No decimal measurements recorded here.",
        )
        self.assertFalse(any(issue.code == "numeric_grounding_mismatch" for issue in issues))

    def test_numeric_grounding_ignores_bibliography_identifier_numbers(self) -> None:
        issues = validate_manuscript(
            "\\section{Related Work} Supported framing.\n"
            "\\begin{thebibliography}{9}\n"
            "\\bibitem{a} Author. Title. doi:10.1007/978-3-031-333333-1_4, pp. 168588.168596.\n"
            "\\end{thebibliography}",
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="No decimal measurements recorded here.",
        )
        self.assertFalse(any(issue.code == "numeric_grounding_mismatch" for issue in issues))

    def test_missing_source_figures_are_warning_not_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            figure = Path(tmp) / "source_figure.pdf"
            figure.write_text("not a real pdf", encoding="utf-8")
            issues = validate_manuscript(
                "Draft cites \\cite{alpha} without reusing every source figure.",
                citation_map={"alpha": {}},
                figures_dir=tmp,
                plot_manifest=None,
                experimental_log_text="",
            )
        figure_issues = [issue for issue in issues if issue.code == "figure_file_not_referenced"]
        self.assertEqual([issue.severity for issue in figure_issues], ["warning"])

    def test_hidden_figure_directory_sentinels_do_not_count_as_source_figures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".gitkeep").write_text("", encoding="utf-8")
            issues = validate_manuscript(
                "Draft cites \\cite{alpha} without external figure files.",
                citation_map={"alpha": {}},
                figures_dir=tmp,
                plot_manifest=None,
                experimental_log_text="",
            )

        self.assertFalse(any(issue.code == "figure_file_not_referenced" for issue in issues))

    def test_expected_section_substance_blocks_heading_only_sections(self) -> None:
        issues = validate_manuscript(
            "\\section{Method}\n\\section{Experiments}\nEnough grounded experiment prose " + "x" * 140,
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=["Method", "Experiments"],
        )
        self.assertTrue(any(issue.code == "expected_section_too_shallow" for issue in issues))

    def test_expected_section_substance_ignores_optional_appendix_titles(self) -> None:
        issues = validate_manuscript(
            "\\section{Method}\n"
            "This section has enough substantive text to avoid shallow section checks. "
            "It describes the construction, assumptions, evaluation scope, and validation boundary in prose.",
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=[
                "Method",
                "Appendix (optional post-template extension)",
                "Appendix A: Details",
                r"\appendix",
                r"\\appendix",
            ],
        )
        self.assertFalse(any(issue.code == "expected_section_missing" for issue in issues))

    def test_expected_section_aliases_accept_common_method_and_experiment_titles(self) -> None:
        issues = validate_manuscript(
            "\\section{Method}\n" + "m" * 180 + "\n\\section{Experiments}\n" + "e" * 180,
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=["Proposed Method", "Implementation and Results"],
        )
        self.assertFalse(any(issue.code == "expected_section_missing" for issue in issues))

    def test_expected_section_aliases_accept_implementation_results_title(self) -> None:
        issues = validate_manuscript(
            "\\section{Method}\n" + "m" * 180 + "\n\\section{Experiments}\n" + "e" * 180,
            citation_map={},
            figures_dir=None,
            plot_manifest=None,
            experimental_log_text="",
            expected_section_titles=["Proposed Method", "Implementation Results"],
        )
        self.assertFalse(any(issue.code == "expected_section_missing" for issue in issues))

    def test_canonicalize_citation_keys_repairs_author_initial_aliases(self) -> None:
        latex, replacements = canonicalize_citation_keys(
            "See \\cite{BCK1996CRYPTO, RFC8446}.",
            citation_map={
                "BellareCanettiKrawczyk1996CRYPTO": {},
                "RFC8446": {},
            },
        )
        self.assertEqual(
            replacements,
            {"BCK1996CRYPTO": "BellareCanettiKrawczyk1996CRYPTO"},
        )
        self.assertIn("\\cite{BellareCanettiKrawczyk1996CRYPTO, RFC8446}", latex)

    def test_build_figure_placement_review_detects_tail_clump_and_missing_hint(self) -> None:
        latex = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "See Figure~\\ref{fig:one} and Figure~\\ref{fig:two}.\n"
            + "\n".join(["Padding line."] * 120)
            + "\n\\begin{figure}\n\\caption{One}\\label{fig:one}\\end{figure}\n"
            "\\begin{figure}\n\\caption{Two}\\label{fig:two}\\end{figure}\n"
            "\\end{document}\n"
        )
        payload = build_figure_placement_review(latex)
        warning_codes = {warning["code"] for warning in payload["warnings"]}
        self.assertIn("tail_clump", warning_codes)
        self.assertIn("placement_hint_missing", warning_codes)

    def test_build_figure_placement_review_marks_source_preserved_and_auto_repaired(self) -> None:
        source = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "\\begin{figure}[t]\n\\caption{Source}\\label{fig:source}\\end{figure}\n"
            "\\end{document}\n"
        )
        latex = (
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Method}\n"
            "\\begin{figure}[t]\n\\caption{Source}\\label{fig:source}\\end{figure}\n"
            "% PaperOrchestra:auto-repaired figure:fig:auto\n"
            "\\begin{figure}[t]\n\\caption{Auto}\\label{fig:auto}\\end{figure}\n"
            "\\end{document}\n"
        )
        payload = build_figure_placement_review(latex, source_latex=source)
        origins = {item["label"]: item["source_origin"] for item in payload["figures"]}
        self.assertEqual(origins["fig:source"], "source_preserved")
        self.assertEqual(origins["fig:auto"], "auto_repaired")


if __name__ == "__main__":
    unittest.main()
