from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from paperorchestra.core.errors import ContractError
from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.literature import mock_verified_paper

LiveVerifier = Callable[..., VerifiedPaper | None]


@dataclass(frozen=True)
class CandidateVerificationResult:
    registry: list[VerifiedPaper]
    errors: list[dict[str, Any]] = field(default_factory=list)
    candidate_count: int = 0


class CandidateVerificationFailure(Exception):
    def __init__(self, *, title: str, original: Exception, errors: list[dict[str, Any]]) -> None:
        super().__init__(str(original))
        self.title = title
        self.original = original
        self.errors = errors


def verify_candidate_registry(
    candidates: dict[str, Any],
    *,
    cutoff_date: str | None,
    mode: str,
    min_ratio: float,
    on_error: str,
    live_verifier: LiveVerifier,
) -> CandidateVerificationResult:
    registry: list[VerifiedPaper] = []
    seen_ids: set[str] = set()
    errors: list[dict[str, Any]] = []
    candidate_count = 0

    for bucket in ["macro_candidates", "micro_candidates"]:
        for candidate in candidates.get(bucket, []):
            title = candidate.get("title_guess")
            if not title:
                continue
            candidate_count += 1
            paper = _verify_one_candidate(
                candidate,
                bucket=bucket,
                title=title,
                cutoff_date=cutoff_date,
                mode=mode,
                min_ratio=min_ratio,
                on_error=on_error,
                live_verifier=live_verifier,
                errors=errors,
            )
            if not paper or paper.is_after_cutoff or paper.paper_id in seen_ids:
                continue
            paper.origin = bucket
            registry.append(paper)
            seen_ids.add(paper.paper_id)

    return CandidateVerificationResult(registry=registry, errors=errors, candidate_count=candidate_count)


def _verify_one_candidate(
    candidate: dict[str, Any],
    *,
    bucket: str,
    title: str,
    cutoff_date: str | None,
    mode: str,
    min_ratio: float,
    on_error: str,
    live_verifier: LiveVerifier,
    errors: list[dict[str, Any]],
) -> VerifiedPaper | None:
    query_hint = candidate.get("origin_query") or title
    if mode == "mock":
        return mock_verified_paper(
            title,
            abstract_hint=candidate.get("why_relevant", ""),
            cutoff_date=cutoff_date,
            origin=bucket,
            query_hint=query_hint,
        )
    if mode != "live":
        raise ContractError(f"Unsupported verify mode: {mode}")

    try:
        return live_verifier(title, cutoff_date=cutoff_date, query_hint=query_hint, min_ratio=min_ratio)
    except Exception as exc:
        error = {
            "bucket": bucket,
            "title_guess": title,
            "query_hint": query_hint,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "action": "failed" if on_error == "fail" else "skipped",
        }
        errors.append(error)
        if on_error == "fail":
            raise CandidateVerificationFailure(title=title, original=exc, errors=errors) from exc
        return None


__all__ = ["CandidateVerificationFailure", "CandidateVerificationResult", "verify_candidate_registry"]
