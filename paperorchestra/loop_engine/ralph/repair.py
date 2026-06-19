from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_latex
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion_env import _build_completion_request
from paperorchestra.engine.completion_runtime import _complete_with_runtime_mode
from paperorchestra.engine.review_stages import compile_current_paper, record_current_validation_report
from paperorchestra.loop_engine.ralph.repair_issue_packet import (
    _claim_safety_repair_issues,
    _non_supported_citation_items,
    _source_obligation_repair_context,
)
from paperorchestra.loop_engine.ralph.repair_prompt import _repair_prompt
from paperorchestra.loop_engine.ralph.repair_recheck_candidate import _candidate_semantic_recheck
from paperorchestra.loop_engine.ralph.repair_runner import CitationClaimRepairRunner
from paperorchestra.runtime.provider_base import BaseProvider
from .state import (
    _read_json,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    atomic_write_text,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    recover_pending_manuscript_write,
)
from paperorchestra.manuscript.citation_alias_rewrite import canonicalize_citation_keys
from paperorchestra.manuscript.citation_key_parsing import extract_citation_keys
from paperorchestra.manuscript.citation_map_model import (
    allowed_citation_keys,
    canonical_citation_map,
)


def repair_citation_claims(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    citation_review_path: str | Path | None = None,
    runtime_mode: str = "compatibility",
    require_compile: bool = False,
    commit: bool = False,
) -> dict[str, Any]:
    return CitationClaimRepairRunner(
        cwd=cwd,
        provider=provider,
        stage=sys.modules[__name__],
        citation_review_path=citation_review_path,
        runtime_mode=runtime_mode,
        require_compile=require_compile,
        commit=commit,
    ).run()


__all__ = ["CitationClaimRepairRunner", "repair_citation_claims"]
