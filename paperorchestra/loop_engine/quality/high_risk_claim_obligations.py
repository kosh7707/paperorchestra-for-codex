from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.high_risk_claim_patterns import BENCHMARK_CLAIM_RE, SECURITY_CLAIM_RE
from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.manuscript.validator import extract_decimal_like_tokens


def _sentence_supported_by_obligation(sentence: str, obligation: dict[str, Any]) -> bool:
    lowered = sentence.lower()
    obligation_type = str(obligation.get("type") or "")
    if SECURITY_CLAIM_RE.search(sentence) and obligation_type not in {
        "security_assumption",
        "theorem_or_bound",
        "proof_step",
        "method_core",
    }:
        return False
    if BENCHMARK_CLAIM_RE.search(sentence) and obligation_type not in {"benchmark_setup", "benchmark_result"}:
        return False
    terms = [str(term).lower() for term in obligation.get("required_terms") or [] if str(term).strip()]
    matched_terms = [term for term in terms if term in lowered]
    required_min = min(len(terms), max(1, 2 if len(terms) >= 3 else len(terms)))
    if len(matched_terms) < required_min:
        return False
    sentence_numbers = extract_decimal_like_tokens(sentence)
    obligation_numbers = {str(token) for token in obligation.get("numeric_tokens") or []}
    if (obligation_type == "benchmark_result" or sentence_numbers) and obligation_numbers:
        return bool(sentence_numbers & obligation_numbers)
    return True


def _load_source_obligations_for_claim_sweep(source_obligations: dict[str, Any]) -> list[dict[str, Any]]:
    """Load usable source obligations even when the coverage check is partially failing.

    ``evaluate_source_obligations`` can fail because one obligation is missing
    from a candidate manuscript.  Treating that as an all-or-nothing signal made
    the high-risk sweep discard every other still-valid author-material
    obligation, causing one local repair regression to cascade into dozens of
    spurious ``high_risk_uncited_claim`` findings.  The sweep only needs the
    obligation matrix to decide whether a sentence is grounded in supplied
    material, so it may use the current, schema-valid matrix unless the matrix
    itself is missing, stale, or legacy/untrusted.
    """
    if not isinstance(source_obligations, dict):
        return []
    failing_codes = {str(code) for code in source_obligations.get("failing_codes") or []}
    if failing_codes & {
        "source_obligations_missing",
        "source_obligations_stale",
        "source_obligations_legacy_untrusted",
    }:
        return []
    payload = _read_json_if_exists(source_obligations.get("path"))
    if not isinstance(payload, dict):
        return []
    return [obligation for obligation in payload.get("obligations") or [] if isinstance(obligation, dict)]
