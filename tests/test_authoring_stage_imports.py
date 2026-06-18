from __future__ import annotations

from paperorchestra.engine import pipeline
from paperorchestra.engine.intro_related_stage import write_intro_related as intro_related_impl
from paperorchestra.engine.refine_stages import refine_current_paper as refine_impl
from paperorchestra.engine.section_writing_stage import write_sections as write_sections_impl


def test_pipeline_imports_authoring_stage_implementations_directly() -> None:
    assert pipeline.write_intro_related is intro_related_impl
    assert pipeline.write_sections is write_sections_impl
    assert pipeline.refine_current_paper is refine_impl
