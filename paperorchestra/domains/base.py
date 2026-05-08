from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

ObligationPattern = tuple[str, str, tuple[str, ...]]
RegexPattern = tuple[str, Pattern[str]]


@dataclass(frozen=True)
class DomainProfile:
    """Domain-specific vocabulary and templates used by deterministic gates.

    The default PaperOrchestra engine must be domain-neutral.  Specialized
    vocabulary belongs in an explicit profile rather than scattered through the
    writer, validator, and reviewer code paths.
    """

    name: str
    obligation_patterns: tuple[ObligationPattern, ...]
    high_risk_claim_re: Pattern[str]
    security_claim_re: Pattern[str]
    benchmark_claim_re: Pattern[str]
    source_critical_patterns: tuple[RegexPattern, ...]
    paper_specific_topic_re: Pattern[str]
    method_seed_re: Pattern[str]
    proof_seed_re: Pattern[str]
    benchmark_seed_re: Pattern[str]
    method_excerpt_re: Pattern[str]
    proof_excerpt_re: Pattern[str]
    benchmark_excerpt_re: Pattern[str]
    method_scope_tail: str
    proof_scope_tail: str
    benchmark_scope_tail: str
    limitation_scope_tail: str
    mock_prior_work_references: tuple[dict[str, object], ...]

    def scope_tail(self, *, claim_type: str, grounding: str, target_section: str) -> str:
        target = target_section.lower()
        if claim_type == "method" or "method" in target:
            return self.method_scope_tail
        if claim_type in {"security", "proof"} or "security" in target or "proof" in target:
            return self.proof_scope_tail
        if claim_type == "benchmark" or grounding == "experimental_log" or any(
            word in target for word in ("experiment", "result", "evaluation", "implementation")
        ):
            return self.benchmark_scope_tail
        if claim_type == "limitation" or grounding == "human_boundary" or "discussion" in target:
            return self.limitation_scope_tail
        return " The statement is scoped to the evidence and assumptions presented in this paper."
