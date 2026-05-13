from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .orchestra_state import NextAction


@dataclass(frozen=True)
class CriticVerdict:
    critic_id: str
    verdict: str
    evidence_links: list[str]
    private_rationale: str | None = field(default=None, repr=False)

    @property
    def valid(self) -> bool:
        return bool(self.evidence_links)


@dataclass
class CriticConsensus:
    status: str
    readiness_band: str | None = None
    verdicts: list[CriticVerdict] = field(default_factory=list)
    next_action: NextAction | None = None
    blocking_reasons: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readiness_band": self.readiness_band,
            "verdicts": [
                {
                    "critic_id": verdict.critic_id,
                    "verdict": verdict.verdict,
                    "evidence_links": list(verdict.evidence_links),
                }
                for verdict in self.verdicts
            ],
            "next_action": self.next_action.to_dict() if self.next_action else None,
            "blocking_reasons": list(self.blocking_reasons),
            "private_safe": True,
        }


class ConsensusPolicy:
    def evaluate(self, verdicts: list[CriticVerdict]) -> CriticConsensus:
        if len(verdicts) < 2:
            return CriticConsensus(
                status="needs_more_critics",
                verdicts=list(verdicts),
                next_action=NextAction(
                    "run_critic_consensus",
                    "at_least_two_critics_required",
                    requires_omx=True,
                    omx_surface="$critic-consensus",
                    risk="high",
                    evidence_required=True,
                ),
            )
        invalid = [verdict for verdict in verdicts if not verdict.valid]
        if invalid:
            return CriticConsensus(
                status="failed",
                verdicts=list(verdicts),
                blocking_reasons=["critic_verdict_missing_evidence_links"],
            )
        verdict_labels = {verdict.verdict for verdict in verdicts[:2]}
        if len(verdict_labels) == 1:
            label = verdicts[0].verdict
            return CriticConsensus(status="pass", readiness_band=label, verdicts=list(verdicts))
        return CriticConsensus(
            status="needs_adjudication",
            verdicts=list(verdicts),
            next_action=NextAction(
                "run_third_critic_adjudication",
                "critic_disagreement",
                requires_omx=True,
                omx_surface="$critic-adjudication",
                risk="high",
                evidence_required=True,
            ),
        )
