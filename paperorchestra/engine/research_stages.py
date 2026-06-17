from __future__ import annotations

from paperorchestra.engine.prior_work_prompt import (
    build_prior_work_context_from_paths as _prior_work_context_from_paths,
)
from paperorchestra.engine.research_discovery_stage import discover_papers
from paperorchestra.engine.research_prior_work_stage import import_prior_work, research_prior_work
from paperorchestra.engine.research_registry import (
    _citation_map_from_registry,
    _merge_live_verified_with_prior_registry,
)
from paperorchestra.engine.research_registry_io import load_prior_citation_registry
from paperorchestra.engine.research_verification_errors import _record_verification_errors
from paperorchestra.engine.research_verification_stage import build_bib, verify_papers

__all__ = [
    "build_bib",
    "discover_papers",
    "import_prior_work",
    "research_prior_work",
    "verify_papers",
]
