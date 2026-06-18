from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paperorchestra.orchestra.executor import ExecutionRecord
from paperorchestra.orchestra.omx_action_requests import (
    OmxExecutionRequest,
    autoresearch_goal_request,
    trace_summary_request,
)
from paperorchestra.orchestra.omx_capabilities import get_omx_action_capability
from paperorchestra.orchestra.omx_evidence import (
    _artifact_refs_are_contained,
    _artifact_refs_from_stdout,
    _has_required_goal_refs,
)
from paperorchestra.orchestra.omx_execution_records import (
    OMX_ADAPTER_NAME,
    blocked_record,
    executed_omx_record,
    failed_omx_record,
    handoff_required_record,
    unsupported_record,
)
from paperorchestra.orchestra.omx_runners import OmxCommandRunner, SubprocessOmxRunner
from paperorchestra.orchestra.state import NextAction, OrchestraState


@dataclass(frozen=True)
class ArtifactRefResolution:
    refs: list[str]
    blocked_reason: str | None = None


class OmxActionExecutor:
    adapter_name = OMX_ADAPTER_NAME

    def __init__(
        self,
        *,
        cwd: Path,
        runner: OmxCommandRunner | None = None,
        timeout_seconds: float = 30.0,
        slug: str | None = None,
    ) -> None:
        self.cwd = Path(cwd).resolve()
        self.runner = runner or SubprocessOmxRunner()
        self.timeout_seconds = timeout_seconds
        self.slug = slug

    def execute(self, action: NextAction, state: OrchestraState) -> ExecutionRecord:
        if action.action_type == "record_trace_summary":
            return self._run_allowlisted(action, trace_summary_request(action))
        if action.action_type == "start_autoresearch_goal":
            plan = autoresearch_goal_request(action, state, slug_override=self.slug)
            if plan.blocked_reason is not None:
                return blocked_record(action, plan.blocked_reason)
            if plan.request is None:
                raise ValueError("Executable OMX request plan is missing its request.")
            return self._run_allowlisted(action, plan.request)
        capability = get_omx_action_capability(action.action_type)
        if capability.capability == "handoff_required":
            return handoff_required_record(action, capability)
        return unsupported_record(action)

    def _run_allowlisted(self, action: NextAction, request: OmxExecutionRequest) -> ExecutionRecord:
        try:
            result = self.runner.run(request.argv, cwd=self.cwd, timeout_seconds=self.timeout_seconds)
        except FileNotFoundError:
            return blocked_record(action, "omx_binary_missing")
        except TimeoutError:
            return blocked_record(action, "omx_command_timeout")
        if result.return_code != 0:
            return failed_omx_record(
                action,
                surface=request.surface,
                argv=request.argv,
                input_payload=request.input_payload,
                result=result,
            )
        refs = self._artifact_refs(request, stdout=result.stdout)
        if refs.blocked_reason is not None:
            return blocked_record(action, refs.blocked_reason)
        return executed_omx_record(
            action,
            surface=request.surface,
            argv=request.argv,
            input_payload=request.input_payload,
            result=result,
            artifact_refs=refs.refs,
        )

    def _artifact_refs(self, request: OmxExecutionRequest, *, stdout: str) -> ArtifactRefResolution:
        if request.artifact_refs is not None:
            return ArtifactRefResolution(list(request.artifact_refs))
        refs = _artifact_refs_from_stdout(stdout)
        if request.expected_slug is not None and not _artifact_refs_are_contained(refs, request.expected_slug):
            return ArtifactRefResolution([], "omx_artifact_ref_outside_goal")
        if request.expected_slug is not None and not _has_required_goal_refs(refs, request.expected_slug):
            return ArtifactRefResolution([], "omx_artifact_refs_missing")
        return ArtifactRefResolution(refs)
