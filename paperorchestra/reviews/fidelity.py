from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript import prompts as prompt_module
from paperorchestra.manuscript.validator import canonical_citation_map
from paperorchestra.reviews.evaluation import (
    EXPECTED_LITERATURE_REVIEW_AXES,
    build_generated_citation_titles,
    build_review_gate_comparison,
    build_session_eval_summary,
    write_citation_partition_request,
)
from paperorchestra.reviews.fidelity_checks import (
    EXPECTED_OUTLINE_KEYS,
    build_fidelity_checks,
    ensure_default_citation_partition_request as _ensure_default_citation_partition_request,
)
from paperorchestra.reviews.fidelity_sources import (
    PAPER_SOURCE_ENV_VAR,
    PAPER_SOURCE_NAME,
    paper_source_candidates as _paper_source_candidates,
)
from paperorchestra.reviews.fidelity_types import (
    FidelityCheck,
    overall_status as _overall_status,
    status_histogram as _status_histogram,
    summary_descriptor as _summary_descriptor,
)
from paperorchestra.reviews.reproducibility import build_reproducibility_audit, write_reproducibility_audit
from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.reproducibility_citations import _citation_surface_health

# Compatibility re-exports for callers that imported helpers from the old monolith.
__all__ = [
    "EXPECTED_LITERATURE_REVIEW_AXES",
    "EXPECTED_OUTLINE_KEYS",
    "PAPER_SOURCE_ENV_VAR",
    "PAPER_SOURCE_NAME",
    "FidelityCheck",
    "_citation_surface_health",
    "_file_sha256",
    "_read_json_if_exists",
    "_paper_source_candidates",
    "_ensure_default_citation_partition_request",
    "_status_histogram",
    "_overall_status",
    "_summary_descriptor",
    "build_generated_citation_titles",
    "build_fidelity_checks",
    "build_review_gate_comparison",
    "build_reproducibility_audit",
    "build_session_eval_summary",
    "canonical_citation_map",
    "prompt_module",
    "read_json",
    "write_citation_partition_request",
    "write_reproducibility_audit",
    "run_fidelity_audit",
]


def run_fidelity_audit(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    checks = build_fidelity_checks(cwd, state)
    histogram = _status_histogram(checks)
    return {
        "session_id": state.session_id,
        "overall_status": _overall_status(checks),
        "status_histogram": histogram,
        "summary_descriptor": _summary_descriptor(checks),
        "checks": [check.to_dict() for check in checks],
    }
