from __future__ import annotations

from typing import Any, Callable

from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_stages import plan_narrative_and_claims
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.manuscript.source_obligations import write_source_obligations
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.loop_engine.ralph.action_dispatch_codes import (
    CITATION_INTEGRITY_REFRESH_CODES,
    CITATION_QUALITY_REFRESH_CODES,
    CITATION_REPAIR_CODES,
    CITATION_SUPPORT_REVIEW_CODES,
    COMPILE_CODES,
    FIGURE_PLACEMENT_REVIEW_CODES,
    NARRATIVE_PLAN_CODES,
    REFINE_CODES,
    REVIEW_REFRESH_CODES,
    SECTION_REVIEW_CODES,
    SOURCE_OBLIGATION_CODES,
    VALIDATION_REFRESH_CODES,
)
from paperorchestra.loop_engine.ralph.action_dispatch_citation_repair import _handle_citation_repair
from paperorchestra.loop_engine.ralph.action_dispatch_manuscript_handlers import (
    _handle_compile,
    _handle_refine,
    _handle_review_refresh,
    _handle_section_review,
    _handle_source_obligations,
)
from paperorchestra.loop_engine.ralph.action_dispatch_refresh_handlers import (
    _handle_citation_integrity_refresh,
    _handle_citation_quality_refresh,
    _handle_citation_support_review,
    _handle_figure_placement_review,
    _handle_narrative_plan,
    _handle_validation_refresh,
)
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.artifacts import (
    _refresh_citation_integrity_for_current_manuscript,
    _try_rebuild_bib_for_citation_quality,
)
from paperorchestra.loop_engine.ralph.citation_candidate_preservation import preserve_citation_candidate_for_approval
from paperorchestra.loop_engine.ralph.repair import repair_citation_claims
from paperorchestra.loop_engine.ralph.state import _artifact_sha, guarded_replace_manuscript_text

ActionHandler = Callable[[str, dict[str, Any], QaLoopActionDispatchContext, _QaLoopActionDispatchState], bool]

ACTION_HANDLER_REGISTRY: tuple[tuple[frozenset[str], ActionHandler], ...] = (
    (frozenset(NARRATIVE_PLAN_CODES), _handle_narrative_plan),
    (frozenset(VALIDATION_REFRESH_CODES), _handle_validation_refresh),
    (frozenset(FIGURE_PLACEMENT_REVIEW_CODES), _handle_figure_placement_review),
    (frozenset(CITATION_SUPPORT_REVIEW_CODES), _handle_citation_support_review),
    (frozenset(CITATION_QUALITY_REFRESH_CODES), _handle_citation_quality_refresh),
    (frozenset(CITATION_INTEGRITY_REFRESH_CODES), _handle_citation_integrity_refresh),
    (frozenset(REVIEW_REFRESH_CODES), _handle_review_refresh),
    (frozenset(COMPILE_CODES), _handle_compile),
    (frozenset(SECTION_REVIEW_CODES), _handle_section_review),
    (frozenset(SOURCE_OBLIGATION_CODES), _handle_source_obligations),
    (frozenset(REFINE_CODES), _handle_refine),
    (frozenset(CITATION_REPAIR_CODES), _handle_citation_repair),
)


def handled_action_codes() -> set[str]:
    return {code for codes, _handler in ACTION_HANDLER_REGISTRY for code in codes}


def handler_for_code(code: str) -> ActionHandler | None:
    for codes, handler in ACTION_HANDLER_REGISTRY:
        if code in codes:
            return handler
    return None
