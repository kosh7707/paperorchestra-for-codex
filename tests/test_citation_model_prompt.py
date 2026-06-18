from __future__ import annotations

import json

import pytest

from paperorchestra.reviews import citation_model_prompt as prompt
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class RecordingProvider(BaseProvider):
    name = "recording"

    def __init__(self, response: str):
        self.response = response
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        return self.response


def _review_item() -> dict[str, object]:
    return {
        "id": "claim-1",
        "sentence": "Prior work studies alert triage.",
        "citation_keys": ["KeyA"],
        "citation_entries": [{"key": "KeyA", "title": "Alert Triage in Practice"}],
        "claim_type": "background",
        "heuristic_support_status": "metadata_only",
        "heuristic_risk": "medium",
        "extra_internal": "must not be sent",
    }


def test_model_citation_review_sends_bounded_prompt_and_returns_trace() -> None:
    provider = RecordingProvider(
        json.dumps(
            {
                "items": [
                    {
                        "id": "claim-1",
                        "support_status": "supported",
                        "risk": "low",
                        "evidence": [],
                    }
                ],
                "research_notes": ["checked"],
            }
        )
    )

    payload = prompt._build_model_citation_review(
        provider=provider,
        items=[_review_item()],
        web_search_required=True,
        retrieved_web_evidence={"claims": [{"id": "claim-1", "evidence": []}]},
    )

    request = provider.requests[0]
    assert "citation-support verifier" in request.system_prompt
    assert "Return JSON only." in request.system_prompt
    assert "web_search_required: true" in request.user_prompt
    assert "pre_review_retrieved_evidence_provided: true" in request.user_prompt
    assert "extra_internal" not in request.user_prompt
    assert payload["items"][0]["id"] == "claim-1"
    assert payload["research_notes"] == ["checked"]
    assert payload["_trace"]["schema_version"] == "citation-support-trace/1"
    assert payload["_trace"]["web_search_required"] is True
    assert len(payload["_trace"]["system_prompt_sha256"]) == 64
    assert len(payload["_trace"]["user_prompt_sha256"]) == 64
    assert len(payload["_trace"]["response_sha256"]) == 64


def test_model_citation_review_malformed_json_falls_back_to_manual_check() -> None:
    provider = RecordingProvider("not json")

    payload = prompt._build_model_citation_review(
        provider=provider,
        items=[_review_item()],
        web_search_required=False,
    )

    assert payload["items"] == [
        {
            "id": "claim-1",
            "support_status": "needs_manual_check",
            "risk": "high",
            "claim_type": "background",
            "evidence": [],
            "reasoning": (
                "Citation-support model review returned malformed JSON; "
                "the cited claim requires manual verification or a rerun."
            ),
            "suggested_fix": "Rerun the citation-support critic or verify this cited sentence manually.",
        }
    ]
    assert payload["research_notes"][0].startswith("Citation-support model review was conservative")
    assert payload["_trace"]["parse_error"] in {"ExtractionError", "JSONDecodeError", "ValueError"}
    assert payload["_trace"]["web_search_required"] is False


def test_model_citation_review_rejects_payload_without_items_array() -> None:
    provider = RecordingProvider('{"research_notes": []}')

    with pytest.raises(ValueError, match="items array"):
        prompt._build_model_citation_review(
            provider=provider,
            items=[_review_item()],
            web_search_required=False,
        )
