from __future__ import annotations

from typing import Any

from paperorchestra.feedback.packet_bindings import _normalized_sha


def _repeats_non_promotable_candidate(
    prior_attempts: list[dict[str, Any]],
    candidate_sha256: str | None,
) -> bool:
    candidate_sha = _normalized_sha(candidate_sha256)
    if not candidate_sha:
        return False
    for prior in prior_attempts:
        if not isinstance(prior, dict) or prior.get("gate_passed") is True:
            continue
        prior_sha = _normalized_sha(prior.get("candidate_sha256"))
        prior_reasons = [str(reason) for reason in prior.get("gate_reasons") or [] if str(reason).strip()]
        if prior_sha and prior_sha == candidate_sha and prior_reasons:
            return True
    return False
