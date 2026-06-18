from __future__ import annotations

from paperorchestra.orchestra.action_plan_evaluation import ActionPlanEvaluation
from paperorchestra.orchestra.state import NextAction, OrchestraState

KNOWN_ACTIONS = [
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_evidence_obligations",
    "show_prewriting_notice",
    "start_autoresearch",
    "start_autoresearch_goal",
    "start_deep_interview",
    "start_ralplan",
    "start_ralph",
    "start_ultraqa",
    "record_trace_summary",
    "run_critic_consensus",
    "run_third_critic_adjudication",
    "re_adjudicate",
    "compile_current",
    "export_current",
    "match_supplied_figures",
    "block",
    "auto_weaken_or_delete_claim",
    "build_scoring_bundle",
]


class ActionPlanner:
    def plan(self, state: OrchestraState, *, objective: str | None = None, strict_omx: bool = False) -> list[NextAction]:
        return ActionPlanEvaluation(state, objective=objective, strict_omx=strict_omx).plan()


__all__ = ["ActionPlanner", "KNOWN_ACTIONS"]
