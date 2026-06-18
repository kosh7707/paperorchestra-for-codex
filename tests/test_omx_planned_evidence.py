from __future__ import annotations

import pytest

from paperorchestra.orchestra import omx_evidence
from paperorchestra.orchestra.research_models import EvidenceResearchMission, ResearchTask


def _mission(*, desired_surface: str | None = "$autoresearch", task_count: int = 1) -> EvidenceResearchMission:
    tasks = []
    if task_count:
        tasks.append(
            ResearchTask(
                task_id="T1",
                task_type="citation_support",
                claim_id="C1",
                claim_type="novelty",
                graph_role="main",
                criticality="high",
                claim_text_sha256="sha256:claim",
                claim_text_label="claim-1",
                obligation_ids=["O1"],
                status="unsupported",
                desired_surface=desired_surface,
            )
        )
    return EvidenceResearchMission(
        schema_version="evidence-research-mission/1",
        status="research_planned" if task_count else "no_research_needed",
        ready=True,
        desired_surface=desired_surface,
        task_count=task_count,
        tasks=tasks,
    )


def test_planned_invocation_evidence_is_public_safe_and_hash_stable() -> None:
    payload = {
        "safe": ["alpha", {"nested": True}],
        "private_secret": "token",
        "raw_text": "private raw",
        "prompt": "private prompt",
        "argv": ["codex", "exec"],
        "executable_command": "codex exec",
    }

    evidence = omx_evidence.build_planned_omx_invocation_evidence(
        surface="$trace",
        purpose="inspect_state",
        input_payload=payload,
        strict_required=False,
    )

    assert evidence.to_public_dict() == {
        "schema_version": "omx-invocation-evidence/1",
        "surface": "$trace",
        "purpose": "inspect_state",
        "strict_required": False,
        "command_or_skill_hash": omx_evidence._sha256_text("$trace"),
        "input_bundle_hash": omx_evidence._sha256_json(
            {
                "safe": ["alpha", {"nested": True}],
                "private_secret": "<redacted>",
                "raw_text": "<redacted>",
                "prompt": "<redacted>",
                "argv": "<redacted>",
                "executable_command": "<redacted>",
            }
        ),
        "output_ref": None,
        "return_code": None,
        "status": "planned",
        "execution_status": "planned_only",
        "private_material_included": False,
        "private_safe_summary": True,
    }


def test_planned_invocation_evidence_rejects_executed_or_private_states() -> None:
    base = dict(
        schema_version="omx-invocation-evidence/1",
        surface="$trace",
        purpose="inspect_state",
        strict_required=True,
        command_or_skill_hash="command-hash",
        input_bundle_hash="input-hash",
    )

    with pytest.raises(ValueError, match="Unsupported planned OMX skill surface"):
        omx_evidence.build_planned_omx_invocation_evidence(surface="$unknown", purpose="x", input_payload={})
    with pytest.raises(ValueError, match="Unsupported OMX invocation evidence schema"):
        omx_evidence.OmxInvocationEvidence(**{**base, "schema_version": "old"})
    with pytest.raises(ValueError, match="cannot report executed"):
        omx_evidence.OmxInvocationEvidence(**{**base, "status": "pass"})
    with pytest.raises(ValueError, match="planned_only"):
        omx_evidence.OmxInvocationEvidence(**{**base, "execution_status": "executed"})
    with pytest.raises(ValueError, match="cannot include a return code"):
        omx_evidence.OmxInvocationEvidence(**{**base, "return_code": 0})
    with pytest.raises(ValueError, match="cannot include an output reference"):
        omx_evidence.OmxInvocationEvidence(**{**base, "output_ref": "out.json"})
    with pytest.raises(ValueError, match="cannot include private material"):
        omx_evidence.OmxInvocationEvidence(**{**base, "private_material_included": True})
    with pytest.raises(ValueError, match="must be private-safe"):
        omx_evidence.OmxInvocationEvidence(**{**base, "private_safe_summary": False})


def test_research_mission_invocation_evidence_builds_only_for_routed_tasks() -> None:
    evidence = omx_evidence.build_research_mission_invocation_evidence(_mission(desired_surface="$autoresearch-goal"))

    assert evidence is not None
    assert evidence.surface == "$autoresearch-goal"
    assert evidence.purpose == "evidence_research"
    assert evidence.strict_required is True
    assert evidence.execution_status == "planned_only"
    assert evidence.private_material_included is False
    assert evidence.input_bundle_hash == omx_evidence._sha256_json(_mission(desired_surface="$autoresearch-goal").to_public_dict())

    assert omx_evidence.build_research_mission_invocation_evidence(_mission(desired_surface=None)) is None
    assert omx_evidence.build_research_mission_invocation_evidence(_mission(task_count=0)) is None
