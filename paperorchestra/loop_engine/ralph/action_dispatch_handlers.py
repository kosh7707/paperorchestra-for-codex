from __future__ import annotations

from typing import Any, Callable

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
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.action_dispatch_general import (
    handle_compile,
    handle_figure_placement_review,
    handle_narrative_plan,
    handle_refine,
    handle_review_refresh,
    handle_section_review,
    handle_source_obligations,
    handle_validation_refresh,
)
from paperorchestra.loop_engine.ralph.action_dispatch_citation_refresh import (
    handle_citation_integrity_refresh,
    handle_citation_quality_refresh,
    handle_citation_support_review,
)
from paperorchestra.loop_engine.ralph.action_dispatch_citation_repair import handle_citation_repair

ActionHandler = Callable[[str, dict[str, Any], QaLoopActionDispatchContext, _QaLoopActionDispatchState], bool]


ACTION_HANDLER_REGISTRY: tuple[tuple[frozenset[str], ActionHandler], ...] = (
    (frozenset(NARRATIVE_PLAN_CODES), handle_narrative_plan),
    (frozenset(VALIDATION_REFRESH_CODES), handle_validation_refresh),
    (frozenset(FIGURE_PLACEMENT_REVIEW_CODES), handle_figure_placement_review),
    (frozenset(CITATION_SUPPORT_REVIEW_CODES), handle_citation_support_review),
    (frozenset(CITATION_QUALITY_REFRESH_CODES), handle_citation_quality_refresh),
    (frozenset(CITATION_INTEGRITY_REFRESH_CODES), handle_citation_integrity_refresh),
    (frozenset(REVIEW_REFRESH_CODES), handle_review_refresh),
    (frozenset(COMPILE_CODES), handle_compile),
    (frozenset(SECTION_REVIEW_CODES), handle_section_review),
    (frozenset(SOURCE_OBLIGATION_CODES), handle_source_obligations),
    (frozenset(REFINE_CODES), handle_refine),
    (frozenset(CITATION_REPAIR_CODES), handle_citation_repair),
)


def handled_action_codes() -> set[str]:
    return {code for codes, _handler in ACTION_HANDLER_REGISTRY for code in codes}


def handler_for_code(code: str) -> ActionHandler | None:
    for codes, handler in ACTION_HANDLER_REGISTRY:
        if code in codes:
            return handler
    return None
