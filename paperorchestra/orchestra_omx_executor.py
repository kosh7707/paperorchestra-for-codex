from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .orchestra_executor import ExecutionRecord
from .orchestra_state import NextAction, OrchestraState

OMX_ACTION_EXECUTION_SCHEMA_VERSION = "omx-action-execution/1"
OMX_ACTION_HANDOFF_SCHEMA_VERSION = "omx-action-handoff/1"
_VALID_SLUG = re.compile(r"^po-[0-9a-f]{12}$")
_VALID_PUBLIC_REASON = re.compile(r"^[a-z0-9_:-]{1,96}$")
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")


@dataclass(frozen=True)
class OmxCommandResult:
    return_code: int
    stdout: str = ""
    stderr: str = ""


class OmxCommandRunner(Protocol):
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        ...


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
    "start_autoresearch": OmxActionCapability(
        "start_autoresearch",
        "handoff_required",
        "$autoresearch",
    ),
    "start_deep_interview": OmxActionCapability(
        "start_deep_interview",
        "handoff_required",
        "$deep-interview",
    ),
    "start_ralplan": OmxActionCapability(
        "start_ralplan",
        "handoff_required",
        "$ralplan",
    ),
    "start_ralph": OmxActionCapability(
        "start_ralph",
        "handoff_required",
        "$ralph",
    ),
    "start_ultraqa": OmxActionCapability(
        "start_ultraqa",
        "handoff_required",
        "$ultraqa",
    ),
    "run_critic_consensus": OmxActionCapability(
        "run_critic_consensus",
        "handoff_required",
        "$critic-consensus",
    ),
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


@dataclass
class FakeOmxRunner:
    results: list[OmxCommandResult] = field(default_factory=list)
    exception: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        self.calls.append({"argv": list(argv), "cwd": str(cwd), "timeout_seconds": timeout_seconds})
        if self.exception is not None:
            raise self.exception
        if self.results:
            return self.results.pop(0)
        return OmxCommandResult(return_code=0, stdout="{}")


@dataclass(frozen=True)
class SubprocessOmxRunner:
    binary: str = "omx"

    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> OmxCommandResult:
        resolved_argv = list(argv)
        if resolved_argv and resolved_argv[0] == "omx":
            resolved_argv[0] = self.binary
        try:
            proc = subprocess.run(
                resolved_argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("omx_command_timeout") from exc
        return OmxCommandResult(return_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


class OmxActionExecutor:
    adapter_name = "omx"

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
            return self._run_allowlisted(
                action,
                state,
                surface="trace_summary",
                argv=["omx", "trace", "summary", "--json"],
                input_payload={"action_type": action.action_type, "reason": _public_reason(action.reason)},
                artifact_refs=[],
            )
        if action.action_type == "start_autoresearch_goal":
            slug = self.slug or _default_slug(action, state)
            if not _valid_public_slug(slug):
                return self._blocked(action, "omx_goal_slug_invalid")
            topic = f"PaperOrchestra evidence research goal {slug}"
            rubric = "PASS if durable evidence research artifacts are public-safe and reviewable."
            argv = [
                "omx",
                "autoresearch-goal",
                "create",
                "--topic",
                topic,
                "--rubric",
                rubric,
                "--slug",
                slug,
                "--json",
            ]
            return self._run_allowlisted(
                action,
                state,
                surface="autoresearch_goal_create",
                argv=argv,
                input_payload={
                    "action_type": action.action_type,
                    "reason": _public_reason(action.reason),
                    "slug": slug,
                    "topic_hash": _sha256_text(topic),
                    "rubric_hash": _sha256_text(rubric),
                },
                artifact_refs=None,
                expected_slug=slug,
            )
        capability = get_omx_action_capability(action.action_type)
        if capability.capability == "handoff_required":
            return self._handoff_required(action, capability)
        return ExecutionRecord(
            action_type=_public_unsupported_action_type(action.action_type),
            reason=_public_reason(action.reason),
            status="unsupported",
            adapter=self.adapter_name,
            evidence_refs=[],
            state_rebuild_required=False,
        )

    def _handoff_required(self, action: NextAction, capability: OmxActionCapability) -> ExecutionRecord:
        reason = _public_reason(action.reason)
        return ExecutionRecord(
            action_type=action.action_type,
            reason=reason,
            status="handoff_required",
            adapter=self.adapter_name,
            evidence_refs=[self._handoff_evidence(action.action_type, reason, capability)],
            state_rebuild_required=False,
        )

    def _run_allowlisted(
        self,
        action: NextAction,
        state: OrchestraState,
        *,
        surface: str,
        argv: list[str],
        input_payload: dict[str, Any],
        artifact_refs: list[str] | None,
        expected_slug: str | None = None,
    ) -> ExecutionRecord:
        try:
            result = self.runner.run(argv, cwd=self.cwd, timeout_seconds=self.timeout_seconds)
        except FileNotFoundError:
            return self._blocked(action, "omx_binary_missing")
        except TimeoutError:
            return self._blocked(action, "omx_command_timeout")
        if result.return_code != 0:
            return ExecutionRecord(
                action_type=action.action_type,
                reason="omx_command_failed",
                status="failed",
                adapter=self.adapter_name,
                evidence_refs=[self._evidence(surface, argv, input_payload, result, [])],
                state_rebuild_required=False,
            )
        refs = list(artifact_refs or [])
        if artifact_refs is None:
            refs = _artifact_refs_from_stdout(result.stdout)
            if expected_slug is not None and not _artifact_refs_are_contained(refs, expected_slug):
                return self._blocked(action, "omx_artifact_ref_outside_goal")
            if expected_slug is not None and not _has_required_goal_refs(refs, expected_slug):
                return self._blocked(action, "omx_artifact_refs_missing")
        return ExecutionRecord(
            action_type=action.action_type,
            reason=_public_reason(action.reason),
            status="executed_omx",
            adapter=self.adapter_name,
            evidence_refs=[self._evidence(surface, argv, input_payload, result, refs)],
            state_rebuild_required=True,
        )

    def _blocked(self, action: NextAction, reason: str) -> ExecutionRecord:
        return ExecutionRecord(
            action_type=action.action_type,
            reason=reason,
            status="blocked",
            adapter=self.adapter_name,
            evidence_refs=[],
            state_rebuild_required=False,
        )

    def _evidence(
        self,
        surface: str,
        argv: list[str],
        input_payload: dict[str, Any],
        result: OmxCommandResult,
        artifact_refs: list[str],
    ) -> dict[str, Any]:
        payload = {
            "schema_version": OMX_ACTION_EXECUTION_SCHEMA_VERSION,
            "action_type": input_payload.get("action_type"),
            "surface": surface,
            "command_hash": _sha256_json({"surface": surface, "argv": argv}),
            "input_bundle_hash": _sha256_json(_public_input_payload(input_payload)),
            "status": "executed_omx" if result.return_code == 0 else "failed",
            "return_code": result.return_code,
            "stdout_hash": _sha256_text(result.stdout),
            "stderr_hash": _sha256_text(result.stderr) if result.stderr else None,
            "artifact_refs": list(artifact_refs),
            "private_safe": True,
        }
        return {"kind": "omx_action_execution", "payload": payload}

    def _handoff_evidence(
        self,
        action_type: str,
        reason: str,
        capability: OmxActionCapability,
    ) -> dict[str, Any]:
        public_summary = {
            "action_type": action_type,
            "surface": capability.surface,
            "capability": capability.capability,
            "reason": reason,
        }
        payload = {
            "schema_version": OMX_ACTION_HANDOFF_SCHEMA_VERSION,
            "action_type": action_type,
            "surface": capability.surface,
            "capability": capability.capability,
            "reason": reason,
            "handoff_summary_hash": _sha256_json(public_summary),
            "private_safe": True,
        }
        return {"kind": "omx_action_handoff", "payload": payload}


def _default_slug(action: NextAction, state: OrchestraState) -> str:
    seed = _sha256_json(
        {
            "action_type": action.action_type,
            "reason": action.reason,
            "cwd": state.cwd,
            "session_id": state.session_id,
            "manuscript_sha256": state.manuscript_sha256,
        }
    )
    return f"po-{seed[:12]}"


def _valid_public_slug(slug: str) -> bool:
    if not _VALID_SLUG.fullmatch(slug):
        return False
    if any(marker in slug.upper() for marker in _PRIVATE_MARKERS):
        return False
    return True


def _artifact_refs_from_stdout(stdout: str) -> list[str]:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return []
    mission = payload.get("mission") if isinstance(payload, dict) else None
    if not isinstance(mission, dict):
        return []
    refs: list[str] = []
    for key in ("mission_path", "rubric_path", "ledger_path", "completion_path"):
        value = mission.get(key)
        if isinstance(value, str):
            refs.append(value)
    return refs


def _artifact_refs_are_contained(refs: list[str], slug: str) -> bool:
    prefix = f".omx/goals/autoresearch/{slug}/"
    for ref in refs:
        path = Path(ref)
        if path.is_absolute() or ".." in path.parts:
            return False
        if not ref.startswith(prefix):
            return False
    return True


def _has_required_goal_refs(refs: list[str], slug: str) -> bool:
    required = {
        f".omx/goals/autoresearch/{slug}/mission.json",
        f".omx/goals/autoresearch/{slug}/rubric.md",
        f".omx/goals/autoresearch/{slug}/ledger.jsonl",
    }
    return required.issubset(set(refs))


def _public_input_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"topic", "rubric", "argv", "prompt", "raw_text"} or key.startswith("private_"):
            result[key] = "<redacted>"
        else:
            result[key] = value
    return result


def _public_reason(reason: str) -> str:
    if not _VALID_PUBLIC_REASON.fullmatch(reason):
        return "runtime_only_interactive_surface"
    upper = reason.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        return "runtime_only_interactive_surface"
    if reason.startswith(("/", "~")) or ".." in Path(reason).parts or reason.startswith(("omx ", "$")):
        return "runtime_only_interactive_surface"
    return reason


def _public_unsupported_action_type(action_type: str) -> str:
    upper = action_type.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        return "<unsupported-action>"
    if action_type.startswith(("omx ", "$", "/", "~")) or any(character.isspace() for character in action_type):
        return "<unsupported-action>"
    if ".." in Path(action_type).parts:
        return "<unsupported-action>"
    return action_type


def _sha256_json(value: Any) -> str:
    return _sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
