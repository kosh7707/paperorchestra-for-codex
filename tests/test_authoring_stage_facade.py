from __future__ import annotations

from paperorchestra.engine import authoring_stages, pipeline
from paperorchestra.engine.intro_related_stage import write_intro_related as intro_related_impl
from paperorchestra.engine.refine_stages import refine_current_paper as refine_impl
from paperorchestra.engine.section_writing_stage import write_sections as write_sections_impl


def test_authoring_stages_facade_preserves_public_imports() -> None:
    assert authoring_stages.write_intro_related is intro_related_impl
    assert authoring_stages.write_sections is write_sections_impl
    assert authoring_stages.refine_current_paper is refine_impl
    assert authoring_stages.__all__ == ["refine_current_paper", "write_intro_related", "write_sections"]


def test_pipeline_preserves_authoring_stage_reexports() -> None:
    assert pipeline.write_intro_related is intro_related_impl
    assert pipeline.write_sections is write_sections_impl
    assert pipeline.refine_current_paper is refine_impl
