from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState, utc_now_iso
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.reviews import citation_integrity as integrity
from paperorchestra.reviews import citation_integrity_support as support


def _write_citation_session(tmp_path: Path, *, session_id: str = "citation-test") -> str:
    paper_path = tmp_path / "paper.tex"
    cited_sentence = r"Prior work motivates the design \\cite{KeyA}."
    paper_path.write_text("\\section{Introduction}\n" + cited_sentence + "\n", encoding="utf-8")
    claim_map_path = tmp_path / "claim_map.json"
    claim_map_path.write_text(
        '{"claims":[{"id":"C1","required_source_type":"prior_work","citation_keys":["KeyA"]}]}',
        encoding="utf-8",
    )
    placement_path = tmp_path / "citation_placement_plan.json"
    placement_path.write_text(
        '{"placements":[{"citation_key":"KeyA","citation_role":"motivation"}]}',
        encoding="utf-8",
    )
    support_path = tmp_path / "citation_support_review.json"
    support_path.write_text(
        '{"items":[{"id":"S1","sentence":"'
        + cited_sentence.replace("\\", "\\\\")
        + '","citation_keys":["KeyA"],"claim_type":"prior_work","support_status":"supported"}]}',
        encoding="utf-8",
    )
    now = utc_now_iso()
    state = SessionState(
        session_id=session_id,
        created_at=now,
        updated_at=now,
        current_phase="review",
        active_artifact="paper.tex",
        inputs=InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
        artifacts=ArtifactIndex(
            paper_full_tex=str(paper_path),
            claim_map_json=str(claim_map_path),
            citation_placement_plan_json=str(placement_path),
        ),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)
    return cited_sentence


def test_v3_support_items_require_readable_text_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_text("supporting passage", encoding="utf-8")

    items = support._support_items_from_v3_cases(
        [
            {"id": "c1", "key": "KeyA", "verdict": "pass", "evidence": {"status": "text", "path": str(evidence_path)}},
            {"id": "c2", "key": "KeyB", "verdict": "pass", "evidence": {"status": "text", "path": "missing.txt"}},
            {"id": "c3", "key": "KeyC", "verdict": "weak", "evidence": {"status": "metadata"}},
        ]
    )

    assert [item["support_status"] for item in items] == [
        "supported",
        "insufficient_evidence",
        "metadata_only",
    ]
    assert items[0]["citation_keys"] == ["KeyA"]


def test_duplicate_support_failures_require_repeated_key_without_distinct_roles() -> None:
    assert support._duplicate_support_failures([], {"A": 4, "B": 4}, {"B": {"motivation", "method"}}) == ["A"]

    items = [
        {"citation_keys": ["C"], "claim_id": "same"},
        {"citation_keys": ["C"], "claim_id": "same"},
        {"citation_keys": ["C"], "claim_id": "same"},
        {"citation_keys": ["C"], "claim_id": "same"},
        {"citation_keys": ["D"], "claim_id": "one"},
        {"citation_keys": ["D"], "claim_id": "two"},
        {"citation_keys": ["D"], "claim_id": "one"},
        {"citation_keys": ["D"], "claim_id": "two"},
    ]

    assert support._duplicate_support_failures(items, {}, {}) == ["C"]


def test_claim_map_context_violations_flag_own_contribution_citations_and_missing_required_sources(monkeypatch) -> None:
    state = SimpleNamespace(artifacts=SimpleNamespace(claim_map_json="claim-map.json"))
    monkeypatch.setattr(
        support,
        "_read_json_if_exists",
        lambda path: {
            "claims": [
                {"id": "own", "claim_type": "own_contribution", "citation_keys": ["A"]},
                {"id": "required", "required_source_type": "prior_work", "citation_keys": []},
                {"id": "optional", "required_source_type": "prior_work", "required": False, "citation_keys": []},
            ]
        },
    )

    assert support._claim_map_context_violations(state) == ["own", "required"]


def test_build_citation_intent_plan_uses_reexported_role_tokens(tmp_path: Path) -> None:
    _write_citation_session(tmp_path, session_id="intent-test")

    payload = integrity.build_citation_intent_plan(tmp_path)

    assert integrity._role_tokens("compat") == {"compat"}
    assert payload["status"] == "pass"
    assert payload["items"][0]["claim_ids"] == ["C1"]
    assert payload["items"][0]["citation_roles"] == ["motivation", "prior_work"]
    assert payload["items"][0]["support_review_item_count"] == 1


def test_write_citation_integrity_audit_keeps_audit_builder_imports_live(tmp_path: Path) -> None:
    _write_citation_session(tmp_path, session_id="audit-test")

    path, payload = integrity.write_citation_integrity_audit(tmp_path)

    assert path.exists()
    assert payload["schema_version"] == "citation-integrity-audit/1"
    assert payload["status"] == "pass"
    assert payload["checks"]["citation_density"]["status"] == "pass"
    assert payload["checks"]["claim_source_match"]["status"] == "pass"
    assert Path(payload["source_artifacts"]["citation_intent_plan"]).exists()
    assert Path(payload["source_artifacts"]["citation_source_match"]).exists()
