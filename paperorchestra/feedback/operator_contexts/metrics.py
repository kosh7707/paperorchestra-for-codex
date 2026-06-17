from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contract import OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES


def _operator_refinement_constraints(
    quality_eval_payload: dict[str, Any] | None,
    citation_integrity_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    before_failing_codes: list[str] = []
    if isinstance(quality_eval_payload, dict):
        tiers = quality_eval_payload.get("tiers") if isinstance(quality_eval_payload.get("tiers"), dict) else {}
        tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
        before_failing_codes.extend(str(code) for code in tier2.get("failing_codes") or [] if str(code).strip())
    if isinstance(citation_integrity_payload, dict):
        before_failing_codes.extend(str(code) for code in citation_integrity_payload.get("failing_codes") or [] if str(code).strip())
    before_failing_codes = sorted(dict.fromkeys(before_failing_codes))
    return {
        "before_failing_codes": before_failing_codes,
        "forbidden_new_tier2_codes": sorted(OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES),
        "hard_constraints": [
            "Use only bibliography keys already present in citation_map.json; do not add new bibliography keys.",
            "Do not use dense citation bundles to hide weak support; split or role-clarify them when they obscure claim support.",
            "Do not introduce weak, unsupported, manual-check, metadata-only, or insufficient-evidence citation support.",
            "Do not introduce new high-risk uncited claims; scope, delete, or ground existing high-risk claims instead.",
            "Reduce duplicate-support and claim-support issues; never make their counts worse.",
        ],
    }

def _compact_metric_delta_records(records: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return result
    for record in records:
        if not isinstance(record, dict):
            continue
        compact = {
            "code": str(record.get("code") or ""),
            "before": record.get("before"),
            "after": record.get("after"),
            "delta": record.get("delta"),
        }
        if compact["code"]:
            result.append(compact)
        if len(result) >= limit:
            break
    return result

def _compact_prior_rejected_attempts(
    attempts: list[dict[str, Any]] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return bounded code/count/hash-only memory for failed operator candidates.

    This memory is fed back into the next supervised operator attempt so the
    refiner can avoid repeating a repair shape that strict gates already
    rejected.  It intentionally omits candidate text, artifact paths, reviewer
    prose, and raw private source locations.
    """
    result: list[dict[str, Any]] = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        if attempt.get("gate_passed") is True:
            continue
        gate_reasons = sorted(dict.fromkeys(str(reason) for reason in attempt.get("gate_reasons") or [] if str(reason).strip()))
        if not gate_reasons:
            continue
        metric_delta = attempt.get("active_tier2_metric_delta") if isinstance(attempt.get("active_tier2_metric_delta"), dict) else {}
        compact: dict[str, Any] = {
            "attempt_index": attempt.get("attempt_index"),
            "candidate_sha256": str(attempt.get("candidate_sha256") or ""),
            "gate_reasons": gate_reasons,
            "resolved_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("resolved_active_failures") or [] if str(code).strip())),
            "new_tier2_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("new_tier2_failures") or [] if str(code).strip())),
            "candidate_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("candidate_active_failures") or [] if str(code).strip())),
            "base_active_failures": sorted(dict.fromkeys(str(code) for code in attempt.get("base_active_failures") or [] if str(code).strip())),
        }
        if isinstance(metric_delta, dict):
            compact["metric_regressions"] = _compact_metric_delta_records(metric_delta.get("regressions"))
            compact["metric_improvements"] = _compact_metric_delta_records(metric_delta.get("improvements"))
            compact["base_total"] = metric_delta.get("base_total")
            compact["candidate_total"] = metric_delta.get("candidate_total")
        result.append(compact)
    return result[-limit:]
