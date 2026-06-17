from __future__ import annotations

import io
import json
from pathlib import Path

from paperorchestra.reviews import citation_model_progress_review as progress_review
from paperorchestra.reviews import citation_model_review
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class SequencedProvider(BaseProvider):
    name = "sequenced"

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        claim_id = "claim-1" if len(self.requests) == 1 else "claim-2"
        return json.dumps(
            {
                "items": [
                    {
                        "id": claim_id,
                        "support_status": "supported",
                        "risk": "low",
                        "evidence": [
                            {
                                "citation_key": "KeyA",
                                "source_title": "Alert Triage in Practice",
                                "evidence_quote_or_summary": "Direct evidence.",
                                "supports_claim": True,
                            }
                        ],
                        "reasoning": f"checked {claim_id}",
                        "suggested_fix": "No change.",
                    }
                ],
                "research_notes": [f"note {claim_id}"],
            }
        )


def _item(item_id: str, key: str = "KeyA") -> dict[str, object]:
    return {
        "id": item_id,
        "sentence": f"Prior work studies alert triage~\\cite{{{key}}}.",
        "citation_keys": [key],
        "citation_entries": [{"key": key, "title": "Alert Triage in Practice"}],
        "claim_type": "background",
        "heuristic_support_status": "metadata_only",
        "heuristic_risk": "medium",
        "support_status": "metadata_only",
        "risk": "medium",
    }


def test_citation_model_review_facade_exports_progress_review_builder() -> None:
    assert citation_model_review._build_model_citation_review_with_progress is progress_review._build_model_citation_review_with_progress


def test_progress_model_review_checkpoint_reuses_completed_claim(tmp_path: Path) -> None:
    provider = SequencedProvider()
    progress_stream = io.StringIO()
    checkpoint = tmp_path / "citation.progress.jsonl"
    items = [_item("claim-1"), _item("claim-2")]

    first = progress_review._build_model_citation_review_with_progress(
        provider=provider,
        items=items,
        web_search_required=False,
        evidence_mode="model",
        manuscript_sha256="sha256:paper",
        citation_map_sha256="sha256:citation-map",
        provider_identity={"provider_name": "sequenced"},
        progress_stream=progress_stream,
        progress_checkpoint_path=checkpoint,
    )
    assert len(provider.requests) == 2
    assert first["_trace"]["checked_claims"] == 2
    assert checkpoint.read_text(encoding="utf-8").count("\n") == 2

    provider2 = SequencedProvider()
    progress_stream2 = io.StringIO()
    second = progress_review._build_model_citation_review_with_progress(
        provider=provider2,
        items=items,
        web_search_required=False,
        evidence_mode="model",
        manuscript_sha256="sha256:paper",
        citation_map_sha256="sha256:citation-map",
        provider_identity={"provider_name": "sequenced"},
        progress_stream=progress_stream2,
        progress_checkpoint_path=checkpoint,
    )

    assert provider2.requests == []
    assert second["_trace"]["reused_claims"] == 2
    assert second["items"] == first["items"]
    assert "reusing 1/2" in progress_stream2.getvalue()
