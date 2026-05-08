from __future__ import annotations

import unittest
from pathlib import Path

from paperorchestra import prompts


class PromptFidelityTests(unittest.TestCase):
    def _render_literature_prompt(self) -> str:
        return prompts.PROMPTS.render_intro_related_system(
            paper_count=17,
            min_cite_paper_count=15,
            cutoff_date="2025-01-01",
        )

    def _rendered_stage_prompts(self) -> list[str]:
        return [
            prompts.PROMPTS.render_outline_system(cutoff_date="2024-11-01"),
            prompts.PROMPTS.render_intro_related_system(
                paper_count=11,
                min_cite_paper_count=10,
                cutoff_date="2024-11-01",
            ),
            prompts.PROMPTS.render_section_writer_system(),
            prompts.PROMPTS.render_refine_system(),
        ]

    def test_prompt_asset_files_exist(self) -> None:
        asset_dir = Path(prompts.__file__).with_name("prompt_assets")
        expected = {
            "outline_agent.md",
            "literature_review_agent.md",
            "section_writing_agent.md",
            "content_refinement_agent.md",
            "literature_review_quality_autorater.md",
            "citation_partition_autorater.md",
            "prompt_fidelity_matrix.md",
        }
        self.assertTrue(expected.issubset({path.name for path in asset_dir.iterdir()}))

    def test_outline_prompt_contains_appendix_f_semantics(self) -> None:
        prompt = prompts.PROMPTS.render_outline_system(cutoff_date="2025-01-01")
        self.assertIn("Global Instruction: Do not analyze inputs in isolation", prompt)
        self.assertIn("Prevent Citation Overlap", prompt)
        self.assertIn("CRITICAL TIMELINE RULE", prompt)
        self.assertIn("citation_hints query for EVERY SINGLE dataset, optimizer, metric", prompt)
        self.assertIn("Strict Output Format (JSON)", prompt)
        self.assertIn("2025-01-01", prompt)
        self.assertNotIn("{cutoff_date}", prompt)

    def test_literature_prompt_contains_citation_and_timeline_rules(self) -> None:
        prompt = self._render_literature_prompt()
        self.assertIn("YOU MUST ONLY CITE THE GIVEN collected_papers", prompt)
        self.assertIn("You MUST cite at least 15", prompt)
        self.assertIn("You have access to the abstract of 17 collected papers", prompt)
        self.assertIn("CRITICAL TIMELINE RULE", prompt)
        self.assertIn("CRITICAL EVALUATION RULE", prompt)
        self.assertIn("cleveref", prompt)
        self.assertIn("2025-01-01", prompt)
        self.assertNotIn("{paper_count}", prompt)
        self.assertNotIn("{min_cite_paper_count}", prompt)
        self.assertNotIn("{cutoff_date}", prompt)

    def test_section_writer_prompt_contains_paper_specific_constraints(self) -> None:
        prompt = prompts.SECTION_WRITER_SYSTEM_PROMPT
        self.assertIn("Your MASTER PLAN", prompt)
        self.assertIn("Do not hallucinate numbers", prompt)
        self.assertIn("You MUST use the exact keys found in the reference library", prompt)
        self.assertIn("Make sure to use ALL of the figures provided", prompt)
        self.assertIn('Do NOT use comparative phrases such as "better than"', prompt)
        self.assertIn("prefer those generated plot assets", prompt)
        self.assertIn("Ensure the LaTeX code compiles without errors", prompt)


    def test_writer_prompts_avoid_boundary_control_terms(self) -> None:
        forbidden = [
            "supplied source material",
            "provided material",
            "source boundary",
            "claim_map",
            "narrative_plan",
            "prompt instructions",
            "generation pipeline",
            "intro_related_work_plan",
            "author_facing_writer_brief.json",
        ]
        for prompt in [
            self._render_literature_prompt(),
            prompts.PROMPTS.render_section_writer_system(),
            prompts.PROMPTS.render_refine_system(),
        ]:
            lower = prompt.lower()
            for phrase in forbidden:
                self.assertNotIn(phrase, lower)

    def test_refinement_prompt_contains_reward_hacking_guards(self) -> None:
        prompt = prompts.PROMPTS.render_refine_system()
        self.assertIn("If the reviewer asks for new experiments", prompt)
        self.assertIn("Your job is purely presentation refinement", prompt)
        self.assertIn("You MUST return your response in two distinct code blocks", prompt)
        self.assertIn("Preserve stated limitations and claim boundaries", prompt)
        self.assertIn("invent new limitations", prompt)

    def test_rendered_stage_prompts_do_not_leak_runtime_placeholders(self) -> None:
        for prompt in self._rendered_stage_prompts():
            self.assertNotIn("{cutoff_date}", prompt)
            self.assertNotIn("{paper_count}", prompt)
            self.assertNotIn("{min_cite_paper_count}", prompt)

    def test_porting_addendum_and_anti_leakage_remain_present(self) -> None:
        for prompt_text in [
            prompts.PROMPTS.render_outline_system(cutoff_date="2025-01-01"),
            prompts.PLOT_SYSTEM_PROMPT,
            self._render_literature_prompt(),
            prompts.PROMPTS.render_section_writer_system(),
            prompts.REVIEW_SYSTEM_PROMPT,
            prompts.PROMPTS.render_refine_system(),
            prompts.PROMPTS.render_literature_review_quality_autorater(avg_citation_count=42),
            prompts.PROMPTS.render_citation_partition_autorater(paper_text="paper body", references_str="[1] Foo"),
        ]:
            self.assertIn("Porting Addendum", prompt_text)
            self.assertIn("Strict knowledge isolation applies", prompt_text)

    def test_literature_review_autorater_prompt_contains_expected_axes(self) -> None:
        prompt = prompts.PROMPTS.render_literature_review_quality_autorater(avg_citation_count=42)
        self.assertIn("Reference Average Citation Count: 42", prompt)
        self.assertIn("Coverage & Completeness", prompt)
        self.assertIn("Critical Analysis & Synthesis", prompt)
        self.assertIn("Citation Practices, Density & Scholarly Rigor", prompt)

    def test_citation_partition_prompt_binds_runtime_placeholders(self) -> None:
        prompt = prompts.PROMPTS.render_citation_partition_autorater(paper_text="paper body", references_str="[1] Foo")
        self.assertIn("paper body", prompt)
        self.assertIn("[1] Foo", prompt)
        self.assertNotIn("{paper_text}", prompt)
        self.assertNotIn("{references_str}", prompt)


if __name__ == "__main__":
    unittest.main()
