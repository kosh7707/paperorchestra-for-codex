from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.orchestra.omx_evidence import _default_slug, _public_reason, _sha256_text, _valid_public_slug
from paperorchestra.orchestra.state import NextAction, OrchestraState

AUTORESEARCH_GOAL_RUBRIC = "PASS if durable evidence research artifacts are public-safe and reviewable."


@dataclass(frozen=True)
class OmxExecutionRequest:
    surface: str
    argv: list[str]
    input_payload: dict[str, Any]
    artifact_refs: list[str] | None
    expected_slug: str | None = None


@dataclass(frozen=True)
class OmxRequestPlan:
    request: OmxExecutionRequest | None = None
    blocked_reason: str | None = None

    @classmethod
    def blocked(cls, reason: str) -> "OmxRequestPlan":
        return cls(request=None, blocked_reason=reason)

    @classmethod
    def executable(cls, request: OmxExecutionRequest) -> "OmxRequestPlan":
        return cls(request=request, blocked_reason=None)


def trace_summary_request(action: NextAction) -> OmxExecutionRequest:
    return OmxExecutionRequest(
        surface="trace_summary",
        argv=["omx", "trace", "summary", "--json"],
        input_payload={"action_type": action.action_type, "reason": _public_reason(action.reason)},
        artifact_refs=[],
    )


def autoresearch_goal_request(action: NextAction, state: OrchestraState, *, slug_override: str | None) -> OmxRequestPlan:
    slug = slug_override or _default_slug(action, state)
    if not _valid_public_slug(slug):
        return OmxRequestPlan.blocked("omx_goal_slug_invalid")
    topic = f"PaperOrchestra evidence research goal {slug}"
    request = OmxExecutionRequest(
        surface="autoresearch_goal_create",
        argv=[
            "omx",
            "autoresearch-goal",
            "create",
            "--topic",
            topic,
            "--rubric",
            AUTORESEARCH_GOAL_RUBRIC,
            "--slug",
            slug,
            "--json",
        ],
        input_payload={
            "action_type": action.action_type,
            "reason": _public_reason(action.reason),
            "slug": slug,
            "topic_hash": _sha256_text(topic),
            "rubric_hash": _sha256_text(AUTORESEARCH_GOAL_RUBRIC),
        },
        artifact_refs=None,
        expected_slug=slug,
    )
    return OmxRequestPlan.executable(request)
