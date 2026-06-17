from __future__ import annotations

from paperorchestra.engine import research_discovery_stage, research_stages


def test_research_stages_facade_reexports_discovery_stage() -> None:
    assert research_stages.discover_papers is research_discovery_stage.discover_papers
