from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine.plan_gate import approve_plan, check_plan_gate, compute_plan_contract_sha256
from paperorchestra.engine.section_writing_context import build_section_prompt_context
from paperorchestra.manuscript.narrative_contracts import planning_source_hashes
from paperorchestra.manuscript.skeleton import (
    build_paper_skeleton_payload,
    paper_skeleton_status,
    read_paper_skeleton_payload,
    validate_paper_skeleton_payload,
    write_paper_skeleton,
)


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def _v3_plan(title: str = "Evidence-grounded SAST triage") -> str:
    return f"""---
schema: paperorchestra/paper-plan/3
revision: 7
plan_id: demo
primary_archetype: systems
target_format: IEEE Transactions
---

# Paper Plan

## Approval summary

- working title: {title}
- one-sentence thesis: Evidence-grounded agent loops can preserve recall while reducing SAST alert review burden.

## Claim-support ledger

| ID | Claim and maximum strength | Claim class | Support mode | Evidence/status | Boundary or wording guard | Destination |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Recall-preserving operation on the configured OWASP run only. | descriptive | internal | E1 provisional | Do not claim general SOTA. | Methodology |
"""


def _approve_plan(tmp_path: Path, *, title: str = "Evidence-grounded SAST triage") -> None:
    text = _v3_plan(title)
    (tmp_path / "paper-plan.md").write_text(text, encoding="utf-8")
    approve_plan(tmp_path)


def _seed_session_with_planning(tmp_path: Path) -> None:
    _approve_plan(tmp_path)
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=_write(tmp_path / "idea.md", "System pipeline proposal for SAST alert triage."),
            experimental_log_path=_write(tmp_path / "experiment.md", "OWASP 2452 alerts, recall target 1.0."),
            template_path=_write(tmp_path / "template.tex", "\\section{Methodology}\\section{Experiment Setup}"),
            guidelines_path=_write(tmp_path / "guide.md", "Use a conventional engineering paper structure."),
        ),
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    citation_map_path = artifact_path(tmp_path, "citation_map.json")
    write_json(outline_path, {"section_plan": [{"section_title": "Methodology"}, {"section_title": "Experiment Setup"}]})
    write_json(citation_map_path, {"iris2024": {"title": "IRIS", "year": 2024}})
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_map_path)
    save_session(tmp_path, state)

    hashes = planning_source_hashes(tmp_path)
    narrative_path = artifact_path(tmp_path, "narrative_plan.json")
    claim_path = artifact_path(tmp_path, "claim_map.json")
    citation_plan_path = artifact_path(tmp_path, "citation_placement_plan.json")
    write_json(
        narrative_path,
        {
            "schema_version": "narrative-plan/1",
            "source_hashes": hashes,
            "section_roles": [
                {
                    "section_title": "Methodology",
                    "role": "Explain the pipeline as a bounded method.",
                    "coverage_requirements": [{"claim_id": "claim-001", "authorial_claim": "bounded method"}],
                    "must_not_claim": ["general SOTA"],
                },
                {"section_title": "Experiment Setup", "role": "Define evidence scope.", "must_not_claim": []},
            ],
            "story_beats": [{"claim_id": "claim-001", "beat": "bounded method"}],
        },
    )
    write_json(
        claim_path,
        {
            "schema_version": "claim-map/1",
            "source_hashes": hashes,
            "claims": [
                {
                    "id": "claim-001",
                    "target_section": "Methodology",
                    "claim_type": "method",
                    "grounding": "source_material",
                    "risk": "high",
                    "authorial_claim": "The system pipeline is described only within the approved SAST triage scope.",
                    "scope_note": "Do not generalize beyond the configured material.",
                    "source_refs": [state.inputs.idea_path],
                }
            ],
        },
    )
    write_json(
        citation_plan_path,
        {
            "schema_version": "citation-placement-plan/1",
            "source_hashes": hashes,
            "placements": [{"claim_id": "claim-001", "citation_keys": ["iris2024"]}],
        },
    )
    state = load_session(tmp_path)
    state.artifacts.narrative_plan_json = str(narrative_path)
    state.artifacts.claim_map_json = str(claim_path)
    state.artifacts.citation_placement_plan_json = str(citation_plan_path)
    save_session(tmp_path, state)


def test_write_paper_skeleton_records_provenance_and_status(tmp_path: Path) -> None:
    _seed_session_with_planning(tmp_path)

    path = write_paper_skeleton(tmp_path)
    payload = read_paper_skeleton_payload(path)
    state = load_session(tmp_path)

    assert state.artifacts.paper_skeleton_md == str(path)
    assert payload["authoritative"] is False
    assert payload["plan"]["contract_sha256"]
    assert payload["sections"][0]["paragraphs"][0]["claim_refs"] == ["claim-001"]
    assert payload["sections"][0]["paragraphs"][0]["citation_refs"] == ["iris2024"]
    assert paper_skeleton_status(tmp_path)["status"] == "pass"


def test_paper_skeleton_status_detects_new_valid_plan_hash(tmp_path: Path) -> None:
    _seed_session_with_planning(tmp_path)
    write_paper_skeleton(tmp_path)

    _approve_plan(tmp_path, title="Changed approved contract")

    status = paper_skeleton_status(tmp_path)

    assert status["status"] == "stale"
    assert status["reason"] == "plan_contract_hash_mismatch"


def test_section_prompt_rejects_stale_recorded_skeleton(tmp_path: Path) -> None:
    _seed_session_with_planning(tmp_path)
    write_paper_skeleton(tmp_path)

    _approve_plan(tmp_path, title="Changed approved contract")
    current_hashes = planning_source_hashes(tmp_path)
    state = load_session(tmp_path)
    for artifact in (
        state.artifacts.narrative_plan_json,
        state.artifacts.claim_map_json,
        state.artifacts.citation_placement_plan_json,
    ):
        payload = read_json(artifact)
        payload["source_hashes"] = current_hashes
        write_json(artifact, payload)

    with pytest.raises(ContractError, match="paper-skeleton"):
        build_section_prompt_context(
            tmp_path,
            load_session(tmp_path),
            selected_sections=[],
            claim_safe=False,
        )


def test_paper_skeleton_status_detects_source_artifact_staleness(tmp_path: Path) -> None:
    _seed_session_with_planning(tmp_path)
    write_paper_skeleton(tmp_path)
    state = load_session(tmp_path)
    Path(state.artifacts.claim_map_json).write_text('{"schema_version":"claim-map/1","source_hashes":{},"claims":[]}\n', encoding="utf-8")

    status = paper_skeleton_status(tmp_path)

    assert status["status"] == "stale"
    assert status["reason"] in {"source_artifact_hash_mismatch", "planning_artifacts_stale"}


def test_write_paper_skeleton_requires_real_approved_plan_even_with_bypass(tmp_path: Path) -> None:
    create_session(
        tmp_path,
        InputBundle(
            idea_path=_write(tmp_path / "idea.md", "Idea."),
            experimental_log_path=_write(tmp_path / "experiment.md", "Experiment."),
            template_path=_write(tmp_path / "template.tex", "\\section{Methodology}"),
            guidelines_path=_write(tmp_path / "guide.md", "Guidelines."),
        ),
    )
    bypass_gate = check_plan_gate(tmp_path, bypass=True)

    with pytest.raises(ContractError, match="approved paper-plan"):
        write_paper_skeleton(tmp_path, gate=bypass_gate)


def test_paper_skeleton_validation_rejects_unknown_claim_refs(tmp_path: Path) -> None:
    _seed_session_with_planning(tmp_path)
    gate_hash = compute_plan_contract_sha256((tmp_path / "paper-plan.md"))
    payload = build_paper_skeleton_payload(
        gate=type(
            "Gate",
            (),
            {
                "plan_path": str(tmp_path / "paper-plan.md"),
                "approval_state": "approved_hashed",
                "approval_revision": 7,
                "contract_sha256": gate_hash,
                "warning": None,
            },
        )(),
        outline={},
        narrative_plan={
            "section_roles": [
                {"section_title": "Methodology", "coverage_requirements": [{"claim_id": "claim-missing"}]}
            ]
        },
        claim_map={"claims": [{"id": "claim-001", "target_section": "Methodology", "authorial_claim": "Known claim."}]},
        citation_placement_plan={"placements": [{"claim_id": "claim-missing", "citation_keys": []}]},
        source_artifacts={},
    )

    with pytest.raises(ContractError, match="unknown claim id"):
        validate_paper_skeleton_payload(payload)
