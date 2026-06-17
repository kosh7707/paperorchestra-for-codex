from __future__ import annotations

from paperorchestra.engine import research_discovery_stage, research_stages


def test_research_stages_facade_reexports_discovery_stage() -> None:
    assert research_stages.discover_papers is research_discovery_stage.discover_papers


def test_research_stages_facade_reexports_verification_stage() -> None:
    from paperorchestra.engine import research_verification_stage

    assert research_stages.verify_papers is research_verification_stage.verify_papers
    assert research_stages.build_bib is research_verification_stage.build_bib


def test_research_stages_facade_reexports_prior_work_stage() -> None:
    from paperorchestra.engine import research_prior_work_stage

    assert research_stages.research_prior_work is research_prior_work_stage.research_prior_work
    assert research_stages.import_prior_work is research_prior_work_stage.import_prior_work
