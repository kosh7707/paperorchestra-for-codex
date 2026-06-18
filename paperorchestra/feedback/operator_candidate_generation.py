from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.feedback.operator_context import _write_operator_review_for_refiner
from paperorchestra.feedback.packet_artifacts import _file_sha256
from paperorchestra.runtime.provider_base import BaseProvider, ProviderError, TransientProviderError

_EXECUTOR_PATH = "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper"


def _generate_operator_candidate(
    cwd: str | Path | None,
    provider: BaseProvider,
    imported: dict[str, Any],
    *,
    require_compile: bool,
    runtime_mode: str,
    quality_mode: str,
    prior_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    redacted_review_path = _write_operator_review_for_refiner(cwd, imported, prior_attempts=prior_attempts)
    state = load_session(cwd)
    previous_review = state.artifacts.latest_review_json
    state.artifacts.latest_review_json = str(redacted_review_path)
    save_session(cwd, state)
    try:
        result = refine_current_paper(
            cwd,
            provider,
            iterations=1,
            require_compile_for_accept=require_compile,
            runtime_mode=runtime_mode,
            claim_safe=quality_mode == "claim_safe",
            candidate_only=True,
        )
    finally:
        state = load_session(cwd)
        state.artifacts.latest_review_json = previous_review
        save_session(cwd, state)
    item = result[-1] if result else {}
    candidate_path = item.get("candidate_path")
    if candidate_path and Path(candidate_path).exists():
        candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    else:
        state = load_session(cwd)
        candidate_path = state.artifacts.paper_full_tex
        candidate_text = Path(candidate_path).read_text(encoding="utf-8") if candidate_path else ""
    item = dict(item)
    item.setdefault("candidate_path", candidate_path)
    item.setdefault("candidate_sha256", _file_sha256(candidate_path))
    item["previous_review_json"] = previous_review
    item["candidate_text"] = candidate_text
    item.setdefault("executor_environment", "in_process")
    item.setdefault("executor_path", _EXECUTOR_PATH)
    item.setdefault("executor_trace_artifact", str(redacted_review_path))
    item.setdefault("executor_failure_category", "none")
    return item


def _executor_failure_category(exc: Exception) -> str:
    if isinstance(exc, TransientProviderError):
        return "provider_transient_retry_exhausted"
    if isinstance(exc, ProviderError):
        return "provider_error"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ContractError):
        message = str(exc).lower()
        if "extract" in message or "latex" in message or "json" in message:
            return "extraction_failed"
        return "contract_error"
    return "unexpected_exception"


def _failed_operator_candidate_result(cwd: str | Path | None, exc: Exception, *, trace_artifact: str | None = None) -> dict[str, Any]:
    state = load_session(cwd)
    candidate_path = state.artifacts.paper_full_tex
    if trace_artifact is None:
        trace_path = artifact_path(cwd, "operator_feedback.executor-error.json")
        write_json(
            trace_path,
            {
                "schema_version": "operator-feedback-executor-error/1",
                "recorded_at": utc_now_iso(),
                "executor_environment": "in_process",
                "executor_path": _EXECUTOR_PATH,
                "executor_failure_category": _executor_failure_category(exc),
                "error_type": type(exc).__name__,
            },
        )
        trace_artifact = str(trace_path)
    return {
        "iteration": 1,
        "accepted": False,
        "candidate_only": True,
        "candidate_path": candidate_path,
        "candidate_sha256": _file_sha256(candidate_path),
        "candidate_text": Path(candidate_path).read_text(encoding="utf-8") if candidate_path and Path(candidate_path).exists() else "",
        "executor_environment": "in_process",
        "executor_path": _EXECUTOR_PATH,
        "executor_trace_artifact": trace_artifact,
        "executor_failure_category": _executor_failure_category(exc),
        "executor_error_type": type(exc).__name__,
    }
