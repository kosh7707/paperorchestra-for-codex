from __future__ import annotations

import io

from paperorchestra.reviews.citation_web_evidence import (
    _build_web_evidence_retrieval,
    _citation_support_retrieved_evidence_sha256,
    _retrieved_web_evidence_for_item_ids,
    _retrieved_web_evidence_is_reusable,
)
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class FakeEvidenceProvider(BaseProvider):
    name = "fake"

    def __init__(self, response: str):
        self.response = response
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        return self.response


def _item(item_id: str = "claim-1") -> dict:
    return {
        "id": item_id,
        "sentence": "The tool reduces alert triage cost~\\cite{triage}.",
        "citation_keys": ["triage"],
        "citation_entries": [{"key": "triage", "title": "Alert Triage in Practice", "url": "https://example.test"}],
        "claim_type": "background",
    }


def test_retrieved_web_evidence_filters_items_by_id_without_mutating_source() -> None:
    payload = {"items": [_item("keep"), _item("drop")], "research_notes": ["note"]}

    filtered = _retrieved_web_evidence_for_item_ids(payload, {"keep"})

    assert [item["id"] for item in filtered["items"]] == ["keep"]
    assert [item["id"] for item in payload["items"]] == ["keep", "drop"]
    assert filtered["research_notes"] == ["note"]


def test_retrieved_web_evidence_reuse_requires_real_evidence_and_clean_trace() -> None:
    reusable = {
        "trace": {"schema_version": "citation-support-retrieval-trace/1"},
        "items": [{"id": "claim-1", "evidence": [{"citation_key": "triage"}]}],
    }

    assert _retrieved_web_evidence_is_reusable(reusable)
    assert not _retrieved_web_evidence_is_reusable({"trace": {"parse_error": "JSONDecodeError"}, "items": reusable["items"]})
    assert not _retrieved_web_evidence_is_reusable({"trace": {}, "items": [{"id": "claim-1", "evidence": []}]})


def test_retrieved_evidence_sha_tracks_item_evidence_and_research_notes() -> None:
    left = _citation_support_retrieved_evidence_sha256(
        [{"id": "claim-1", "evidence": [{"citation_key": "triage"}]}],
        ["note"],
    )
    right = _citation_support_retrieved_evidence_sha256(
        [{"id": "claim-1", "evidence": [{"citation_key": "triage"}]}],
        ["note"],
    )
    changed = _citation_support_retrieved_evidence_sha256(
        [{"id": "claim-1", "evidence": [{"citation_key": "other"}]}],
        ["note"],
    )

    assert left == right
    assert left != changed


def test_build_web_evidence_retrieval_normalizes_provider_payload_and_progress() -> None:
    provider = FakeEvidenceProvider(
        """
        {
          "items": [
            {
              "id": "claim-1",
              "evidence": [
                {
                  "citation_key": "triage",
                  "source_title": "Alert Triage in Practice",
                  "url": "https://example.test",
                  "summary": "The paper discusses alert triage cost.",
                  "supports": "yes"
                }
              ]
            }
          ],
          "research_notes": ["looked up cited source"]
        }
        """
    )
    progress = io.StringIO()

    result = _build_web_evidence_retrieval(provider=provider, items=[_item()], progress_stream=progress)

    assert provider.requests
    assert result["schema_version"] == "citation-support-retrieved-evidence/1"
    assert result["items"][0]["evidence"] == [
        {
            "citation_key": "triage",
            "source_title": "Alert Triage in Practice",
            "url": "https://example.test",
            "evidence_quote_or_summary": "The paper discusses alert triage cost.",
            "supports_claim": True,
        }
    ]
    assert result["research_notes"] == ["looked up cited source"]
    assert "retrieving 1-1/1" in progress.getvalue()
    assert "retrieved 1-1/1" in progress.getvalue()
