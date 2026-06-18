from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.feedback.operator_contexts.citation_protection_regressions import (
    _protected_supported_citation_regressions,
)
from paperorchestra.feedback.operator_candidate_hard_gate import _candidate_hard_gate
from paperorchestra.feedback.operator_failure_repetition import _repeats_non_promotable_candidate
from paperorchestra.feedback.operator_metric_delta import _active_tier2_metric_delta
from paperorchestra.feedback.operator_incorporation import _issue_incorporation_detailed
from paperorchestra.feedback.operator_quality_codes import _quality_failing_codes, _tier_failing_codes
from paperorchestra.feedback.operator_records import _build_operator_attempt_record
from paperorchestra.feedback.operator_verification import _verification_block, _verification_snapshot
from paperorchestra.feedback.packet_artifacts import _file_sha256, _sha256_digest, _sha256_prefixed


@dataclass(frozen=True)
class OperatorAttemptEvaluation:
    verification: dict[str, Any]
    incorporation: list[dict[str, Any]]
    candidate_result: dict[str, Any]
    gate_passed: bool
    gate_reasons: list[str]
    attempt_record: dict[str, Any]


def evaluate_operator_candidate_attempt(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    imported: dict[str, Any],
    before_text: str,
    current_sha: str,
    base_quality_eval: dict[str, Any] | None,
    base_tier2_failures: set[str],
    base_active_failures: set[str],
    packet_prior_attempts: list[dict[str, Any]],
    execution: dict[str, Any],
    intent: str,
    attempt_index: int,
    candidate_result: dict[str, Any],
    candidate_text: str,
    require_issue_progress: bool,
    require_compile: bool,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
) -> OperatorAttemptEvaluation:
    verification = _verification_snapshot(
        cwd,
        provider=provider,
        require_compile=require_compile,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        runtime_mode=runtime_mode,
        citation_evidence_mode=citation_evidence_mode,
        citation_provider_name=citation_provider_name,
        citation_provider_command=citation_provider_command,
        validation_name=f"validation.operator-feedback.attempt-{attempt_index:02d}.json",
    )
    blocking_codes = _quality_failing_codes(verification["quality_eval"])
    candidate_tier2_failures = set(_tier_failing_codes(verification["quality_eval"], "tier_2_claim_safety"))
    candidate_active_failures = set(blocking_codes)
    new_tier2_failures = sorted(candidate_tier2_failures - base_tier2_failures)
    resolved_active_failures = sorted(base_active_failures - candidate_active_failures)
    incorporation_blocking_codes = [code for code in blocking_codes if code not in base_tier2_failures]
    incorporation = _issue_incorporation_detailed(
        imported.get("issues") or [],
        before_text,
        candidate_text,
        blocking_codes=incorporation_blocking_codes,
    )
    candidate_sha = _file_sha256(load_session(cwd).artifacts.paper_full_tex)
    protected_regressions = _protected_supported_citation_regressions(imported, candidate_text)
    ok, gate_reasons = _candidate_hard_gate(
        validation_payload=verification["validation_payload"],
        compile_payload=verification["compile_payload"],
        quality_eval=verification["quality_eval"],
        base_quality_eval=base_quality_eval,
        quality_mode=quality_mode,
        incorporation=incorporation,
        candidate_result=candidate_result,
        require_issue_progress=require_issue_progress,
        manuscript_changed=candidate_sha != current_sha,
        new_tier2_failures=new_tier2_failures,
        base_active_failures=sorted(base_active_failures),
        resolved_active_failures=resolved_active_failures,
        allow_human_reviewable_new_tier2=intent == "approve_existing_candidate",
        protected_supported_citation_regressions=protected_regressions,
    )
    if candidate_result.get("preserved_prior_after_contract_regression") is True:
        gate_reasons = list(dict.fromkeys([*gate_reasons, "contract_regression_preserved_prior"]))
        ok = False
    candidate_sha_for_attempt = _sha256_prefixed(
        _sha256_digest(str(candidate_result.get("candidate_sha256") or ""))
        or _file_sha256(candidate_result.get("candidate_path"))
    )
    if not ok and _repeats_non_promotable_candidate(
        [*packet_prior_attempts, *(execution.get("attempts") or [])],
        candidate_sha_for_attempt,
    ):
        gate_reasons = list(dict.fromkeys([*gate_reasons, "repeated_non_promotable_candidate"]))
        ok = False
    attempt_record = _build_operator_attempt_record(
        attempt_index=attempt_index,
        intent=intent,
        candidate_result=candidate_result,
        candidate_sha_for_attempt=candidate_sha_for_attempt,
        gate_passed=ok,
        gate_reasons=gate_reasons,
        base_tier2_failures=base_tier2_failures,
        candidate_tier2_failures=candidate_tier2_failures,
        new_tier2_failures=new_tier2_failures,
        base_active_failures=base_active_failures,
        candidate_active_failures=candidate_active_failures,
        resolved_active_failures=resolved_active_failures,
        active_tier2_metric_delta=_active_tier2_metric_delta(
            base_quality_eval,
            verification["quality_eval"],
            base_active_failures=sorted(base_active_failures),
        ),
        protected_regressions=protected_regressions,
        verification_block=_verification_block(verification),
        incorporation=incorporation,
    )
    return OperatorAttemptEvaluation(
        verification=verification,
        incorporation=incorporation,
        candidate_result=candidate_result,
        gate_passed=ok,
        gate_reasons=gate_reasons,
        attempt_record=attempt_record,
    )
