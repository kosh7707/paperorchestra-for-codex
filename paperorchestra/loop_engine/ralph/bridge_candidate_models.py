from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.candidate_outcomes import CandidateOutcome


@dataclass(frozen=True)
class PostActionState:
    eval_path: str | Path
    eval_payload: dict[str, Any]
    plan_path: str | Path
    plan_payload: dict[str, Any]
    summary: dict[str, Any]
    progress: dict[str, Any]
    verification: dict[str, Any]
    verdict: str


@dataclass(frozen=True)
class CandidateResolutionRequest:
    cwd: str | Path | None
    paper_path: Path | None
    original_paper: str | None
    mutation_snapshot: dict[str, Any]
    citation_review_snapshot: dict[str, Any]
    citation_trace_snapshot: dict[str, Any]
    require_compile: bool
    require_live_verification: bool
    quality_mode: str
    max_iterations: int
    accept_mixed_provenance: bool
    before_eval: dict[str, Any]
    before_summary: dict[str, Any]
    actions_attempted: bool
    candidate_outcome: CandidateOutcome
    candidate_path: str | None
    candidate_state: dict[str, Any] | None
    candidate_progress: dict[str, Any]
    auto_commit_reason: str
    residual_citation_failures: list[str]
    after_codes: set[str]


@dataclass(frozen=True)
class CandidateResolutionResult:
    final_eval_path: str | Path
    final_eval: dict[str, Any]
    final_plan_path: str | Path
    final_plan: dict[str, Any]
    final_summary: dict[str, Any]
    final_progress: dict[str, Any]
    final_verification: dict[str, Any]
    verdict: str
    execution_updates: dict[str, Any] = field(default_factory=dict)
