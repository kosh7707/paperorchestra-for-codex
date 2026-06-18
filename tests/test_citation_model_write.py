from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.reviews.citation_model_cache import _citation_support_cache_dir
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class RecordingCitationProvider(BaseProvider):
    name = "recording"

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        return json.dumps(
            {
                "items": [
                    {
                        "id": "cite-001",
                        "support_status": "supported",
                        "risk": "low",
                        "evidence": [
                            {
                                "citation_key": "KeyA",
                                "source_title": "Alert Triage in Practice",
                                "evidence_quote_or_summary": "The paper studies alert triage.",
                                "supports_claim": True,
                            }
                        ],
                        "reasoning": "Directly supported.",
                        "suggested_fix": "No change.",
                    }
                ],
                "research_notes": ["checked source"],
            }
        )


class WebCachingCitationProvider(BaseProvider):
    name = "web-recording"

    def __init__(self, *, reusable_retrieval: bool = True) -> None:
        self.reusable_retrieval = reusable_retrieval
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        if "citation-support evidence retriever" in request.system_prompt:
            evidence = (
                [
                    {
                        "citation_key": "KeyA",
                        "source_title": "Alert Triage in Practice",
                        "url": "https://example.test/key-a",
                        "evidence_quote_or_summary": "The paper studies alert triage.",
                        "supports_claim": True,
                    }
                ]
                if self.reusable_retrieval
                else []
            )
            return json.dumps(
                {
                    "items": [{"id": "cite-001", "evidence": evidence}],
                    "research_notes": ["retrieved source evidence"],
                }
            )
        return json.dumps(
            {
                "items": [
                    {
                        "id": "cite-001",
                        "support_status": "supported",
                        "risk": "low",
                        "evidence": [
                            {
                                "citation_key": "KeyA",
                                "source_title": "Alert Triage in Practice",
                                "url": "https://example.test/key-a",
                                "evidence_quote_or_summary": "The paper studies alert triage.",
                                "supports_claim": True,
                            }
                        ],
                        "reasoning": "Directly supported by retrieved evidence.",
                        "suggested_fix": "No change.",
                    }
                ],
                "research_notes": ["checked retrieved evidence"],
            }
        )


def _session(tmp_path: Path) -> SessionState:
    paper = tmp_path / "paper.full.tex"
    paper.write_text(r"Prior work studies alert triage~\cite{KeyA}.", encoding="utf-8")
    citation_map = tmp_path / "citation_map.json"
    citation_map.write_text(json.dumps({"KeyA": {"title": "Alert Triage in Practice"}}), encoding="utf-8")
    now = utc_now_iso()
    state = SessionState(
        session_id="citation-write-test",
        created_at=now,
        updated_at=now,
        current_phase="review",
        active_artifact=None,
        inputs=InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
        artifacts=ArtifactIndex(
            paper_full_tex=str(paper),
            citation_map_json=str(citation_map),
        ),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)
    return state


def test_write_citation_support_review_copies_model_trace_into_cache(tmp_path: Path) -> None:
    _session(tmp_path)
    provider = RecordingCitationProvider()

    review_path = write_citation_support_review(tmp_path, provider=provider, evidence_mode="model")

    assert review_path.exists()
    trace_path = review_path.with_name("citation_support_review.trace.json")
    assert trace_path.exists()
    cache_traces = list(_citation_support_cache_dir(tmp_path).glob("*.trace.json"))
    assert cache_traces
    assert cache_traces[0].read_text(encoding="utf-8") == trace_path.read_text(encoding="utf-8")
    assert provider.requests


def test_write_citation_support_review_reuses_model_cache_without_provider_call(tmp_path: Path) -> None:
    _session(tmp_path)
    first_provider = RecordingCitationProvider()
    second_provider = RecordingCitationProvider()

    first_path = write_citation_support_review(tmp_path, provider=first_provider, evidence_mode="model")
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    first_trace = first_path.with_name("citation_support_review.trace.json").read_text(encoding="utf-8")

    second_path = write_citation_support_review(tmp_path, provider=second_provider, evidence_mode="model")
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))
    second_trace = second_path.with_name("citation_support_review.trace.json").read_text(encoding="utf-8")

    assert first_provider.requests
    assert second_provider.requests == []
    assert first_payload == second_payload
    assert first_trace == second_trace


def test_write_citation_support_review_reuses_web_retrieval_and_review_cache(tmp_path: Path) -> None:
    _session(tmp_path)
    first_provider = WebCachingCitationProvider()
    second_provider = WebCachingCitationProvider()

    first_path = write_citation_support_review(tmp_path, provider=first_provider, evidence_mode="web")
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    first_trace = first_path.with_name("citation_support_review.trace.json").read_text(encoding="utf-8")
    cache_dir = _citation_support_cache_dir(tmp_path)

    second_path = write_citation_support_review(tmp_path, provider=second_provider, evidence_mode="web")
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))
    second_trace = second_path.with_name("citation_support_review.trace.json").read_text(encoding="utf-8")

    assert len(first_provider.requests) == 2
    assert second_provider.requests == []
    assert first_payload == second_payload
    assert first_trace == second_trace
    assert list(cache_dir.glob("*.retrieved-evidence.json"))
    assert list(cache_dir.glob("*.request.json"))


def test_write_citation_support_review_skips_web_cache_for_nonreusable_retrieval(tmp_path: Path) -> None:
    _session(tmp_path)
    provider = WebCachingCitationProvider(reusable_retrieval=False)

    review_path = write_citation_support_review(tmp_path, provider=provider, evidence_mode="web")
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    provenance = payload["evidence_provenance"]
    cache_dir = _citation_support_cache_dir(tmp_path)

    assert len(provider.requests) == 2
    assert provenance.get("retrieved_web_evidence_sha256")
    assert "cache_key_sha256" not in provenance
    assert list(cache_dir.glob("*.retrieved-evidence.json"))
    assert not list(cache_dir.glob("*.request.json"))
    assert not list(cache_dir.glob("*.trace.json"))
    cache_payloads = [
        path
        for path in cache_dir.glob("*.json")
        if not path.name.endswith(".retrieved-evidence.json")
    ]
    assert cache_payloads == []
