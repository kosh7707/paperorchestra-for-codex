from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session import load_session, save_session, set_current_session
from paperorchestra.reviews import citation_model_cache as cache
from paperorchestra.runtime.provider_base import BaseProvider


class FakeProvider(BaseProvider):
    name = "fake"


def test_citation_support_cache_key_tracks_inputs_and_provider_identity(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("hello", encoding="utf-8")
    citation_map = tmp_path / "citation_map.json"
    citation_map.write_text('{"A":{"title":"Paper"}}', encoding="utf-8")
    state = SimpleNamespace(
        session_id="s1",
        artifacts=SimpleNamespace(
            paper_full_tex=str(paper),
            citation_map_json=str(citation_map),
        ),
    )
    provider = FakeProvider()

    base = cache._citation_support_cache_key(state, provider, "model")
    assert base == cache._citation_support_cache_key(state, provider, "model")
    assert base != cache._citation_support_cache_key(state, provider, "web")
    assert base != cache._citation_support_cache_key(
        state,
        provider,
        "web",
        retrieved_web_evidence_sha256="sha-web",
    )
    citation_map.write_text('{"A":{"title":"Changed"}}', encoding="utf-8")
    assert base != cache._citation_support_cache_key(state, provider, "model")


def test_provider_identity_keeps_generic_provider_public_fields_only() -> None:
    identity = cache._citation_support_provider_identity(FakeProvider())

    assert identity == {
        "provider_name": "fake",
        "provider_command_digest": None,
        "provider_class": "FakeProvider",
    }
    assert cache._citation_support_provider_identity(None) == {
        "provider_name": None,
        "provider_command_digest": None,
        "provider_class": None,
    }


def test_reuse_cached_citation_review_copies_payload_trace_and_updates_session(tmp_path: Path) -> None:
    now = utc_now_iso()
    state = SessionState(
        session_id="cache-test",
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
        artifacts=ArtifactIndex(),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)

    output_path = tmp_path / ".paper-orchestra" / "runs" / state.session_id / "artifacts" / "citation_support_review.json"
    target_trace_path = output_path.with_name("citation_support_review.trace.json")
    cache_payload_path = tmp_path / "cache.json"
    cache_trace_path = tmp_path / "cache.trace.json"
    cache_payload_path.write_text(
        json.dumps(
            {
                "schema_version": "citation-support-review/2",
                "evidence_provenance": {"review_trace_path": str(target_trace_path)},
                "items": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cache_trace_path.write_text('{"trace": true}', encoding="utf-8")

    reused = cache._reuse_cached_citation_review(
        cwd=tmp_path,
        state=state,
        output_path=output_path,
        cache_payload_path=cache_payload_path,
        cache_trace_path=cache_trace_path,
        evidence_mode="model",
        note_suffix="unit cache",
    )

    assert reused == output_path
    assert output_path.exists()
    assert target_trace_path.read_text(encoding="utf-8") == '{"trace": true}'
    saved = load_session(tmp_path, state.session_id)
    assert saved.notes[-1] == "Citation-support critic artifact reused from unit cache: citation_support_review.json (mode=model)"
