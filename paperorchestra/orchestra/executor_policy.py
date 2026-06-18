from __future__ import annotations

from paperorchestra.orchestra.executor_records import ActionCapability
from paperorchestra.orchestra.state import NextAction

LOCAL_SUPPORTED_ACTIONS = {
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
}
FAKE_SUPPORTED_ACTIONS = {
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_scoring_bundle",
    "block",
}
OMX_ACTION_SURFACES = {
    "start_autoresearch": "$autoresearch",
    "start_autoresearch_goal": "$autoresearch-goal",
    "start_deep_interview": "$deep-interview",
    "start_ralplan": "$ralplan",
    "start_ralph": "$ralph",
    "start_ultraqa": "$ultraqa",
    "record_trace_summary": "$trace",
    "run_critic_consensus": "$critic-consensus",
    "run_third_critic_adjudication": "$critic-adjudication",
}
ADAPTER_REQUIRED_ACTIONS = {
    "provide_material",
    "build_evidence_obligations",
    "show_prewriting_notice",
    "re_adjudicate",
    "auto_weaken_or_delete_claim",
    "compile_current",
    "export_current",
    "match_supplied_figures",
}
TERMINAL_BLOCK_ACTIONS = {"block"}
ALLOWED_RISKS = {"low", "medium", "high"}


class ActionExecutionPolicy:
    def classify(self, action: NextAction) -> ActionCapability:
        action_type = action.action_type
        risk = _normalize_risk(action.risk)
        if action_type in LOCAL_SUPPORTED_ACTIONS:
            return ActionCapability(action_type=action_type, execution_kind="local_supported", adapter_hint="local", risk=risk)
        if action_type in OMX_ACTION_SURFACES:
            return ActionCapability(
                action_type=action_type,
                execution_kind="omx_required",
                adapter_hint="omx",
                requires_omx=True,
                omx_surface=OMX_ACTION_SURFACES[action_type],
                risk=risk,
            )
        if action_type in ADAPTER_REQUIRED_ACTIONS:
            return ActionCapability(action_type=action_type, execution_kind="adapter_required", adapter_hint="paperorchestra", risk=risk)
        if action_type in TERMINAL_BLOCK_ACTIONS:
            return ActionCapability(action_type=action_type, execution_kind="terminal_block", adapter_hint="none", risk=risk)
        return ActionCapability(action_type=action_type, execution_kind="unsupported", adapter_hint="none", risk=risk)


def _normalize_risk(risk: str) -> str:
    return risk if risk in ALLOWED_RISKS else "unknown"
