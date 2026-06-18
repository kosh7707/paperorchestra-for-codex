from __future__ import annotations


class InteractionPolicy:
    def classify_gap(self, *, gap_type: str, criticality: str = "medium") -> str:
        if gap_type in {"citation", "source", "reference", "related_work", "novelty"}:
            return "research_needed" if criticality != "durable" else "durable_research_needed"
        if gap_type in {"claim_strategy", "contribution_framing", "central_conflict"}:
            return "human_needed"
        return "research_needed"
