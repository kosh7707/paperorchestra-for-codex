from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OmxActionCapability:
    action_type: str
    capability: str
    surface: str | None
    runner_required: bool = False
    success_possible: bool = False


OMX_ACTION_CAPABILITIES: dict[str, OmxActionCapability] = {
    "record_trace_summary": OmxActionCapability(
        "record_trace_summary",
        "executable",
        "trace_summary",
        runner_required=True,
        success_possible=True,
    ),
    "start_autoresearch_goal": OmxActionCapability(
        "start_autoresearch_goal",
        "executable",
        "autoresearch_goal_create",
        runner_required=True,
        success_possible=True,
    ),
    "start_autoresearch": OmxActionCapability("start_autoresearch", "handoff_required", "$autoresearch"),
    "start_deep_interview": OmxActionCapability("start_deep_interview", "handoff_required", "$deep-interview"),
    "start_ralplan": OmxActionCapability("start_ralplan", "handoff_required", "$ralplan"),
    "start_ralph": OmxActionCapability("start_ralph", "handoff_required", "$ralph"),
    "start_ultraqa": OmxActionCapability("start_ultraqa", "handoff_required", "$ultraqa"),
    "run_critic_consensus": OmxActionCapability("run_critic_consensus", "handoff_required", "$critic-consensus"),
    "run_third_critic_adjudication": OmxActionCapability(
        "run_third_critic_adjudication",
        "handoff_required",
        "$critic-adjudication",
    ),
}


def get_omx_action_capability(action_type: str) -> OmxActionCapability:
    capability = OMX_ACTION_CAPABILITIES.get(action_type)
    if capability is not None:
        return capability
    return OmxActionCapability(
        action_type=action_type,
        capability="unsupported",
        surface=None,
        runner_required=False,
        success_possible=False,
    )
